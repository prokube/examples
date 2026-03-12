from typing import Dict, List

from kfp import dsl
from kfp.dsl import HTML, Input, Output, Dataset, Artifact, Model, ClassificationMetrics, Markdown


COMPONENTS_IMAGE = "europe-west3-docker.pkg.dev/prokube-internal/prokube-customer/mobile-price-classification:v1"


@dsl.component(base_image=COMPONENTS_IMAGE)
def read_data(
    minio_train_data_path: str,
    minio_test_data_path: str,
    train_df: Output[Dataset],
    test_df: Output[Dataset],
):
    """Reads training and test data and writes it to pipeline artifacts as parquet."""
    from mobile_price_classification import read_data as _read_data

    _read_data(
        minio_train_data_path=minio_train_data_path,
        minio_test_data_path=minio_test_data_path,
        train_output_path=train_df.path,
        test_output_path=test_df.path,
    )


@dsl.component(base_image=COMPONENTS_IMAGE)
def split_data(
    train_df: Input[Dataset],
    x_train_df: Output[Dataset],
    y_train_df: Output[Dataset],
    x_val_df: Output[Dataset],
    y_val_df: Output[Dataset],
    test_size: float = 0.5,
    seed: int = 42,
):
    """Splits the provided dataset into training and validation sets."""
    from mobile_price_classification import split_data as _split_data

    _split_data(
        train_df_path=train_df.path,
        x_train_output_path=x_train_df.path,
        y_train_output_path=y_train_df.path,
        x_val_output_path=x_val_df.path,
        y_val_output_path=y_val_df.path,
        test_size=test_size,
        seed=seed,
    )


@dsl.component(base_image=COMPONENTS_IMAGE)
def fit_scaler(train_x: Input[Dataset], fitted_scaler: Output[Artifact]):
    """Fits a MinMaxScaler on the provided training data and saves the fitted scaler."""
    from mobile_price_classification import fit_scaler as _fit_scaler

    _fit_scaler(
        train_x_path=train_x.path,
        fitted_scaler_output_path=fitted_scaler.path,
    )


@dsl.component(base_image=COMPONENTS_IMAGE)
def tune_hyperparams(
    train_x: Input[Dataset],
    train_y: Input[Dataset],
    fitted_scaler: Input[Artifact],
    C: List = [1, 0.1, 0.25, 0.5, 2, 0.75],
    kernel: List = ["linear", "rbf"],
    gamma: List = ["auto", 0.01, 0.001, 0.0001, 1],
    decision_function_shape: List[str] = ["ovo", "ovr"],
    seed: int = 42,
) -> dict:
    """Performs hyperparameter tuning using GridSearchCV for an SVM classifier."""
    from mobile_price_classification import tune_hyperparams as _tune_hyperparams

    return _tune_hyperparams(
        train_x_path=train_x.path,
        train_y_path=train_y.path,
        fitted_scaler_path=fitted_scaler.path,
        C=C,
        kernel=kernel,
        gamma=gamma,
        decision_function_shape=decision_function_shape,
        seed=seed,
    )


@dsl.component(base_image=COMPONENTS_IMAGE)
def train_model(
    train_x: Input[Dataset],
    train_y: Input[Dataset],
    fitted_scaler: Input[Artifact],
    hparams: Dict,
    trained_model: Output[Model],
    seed: int = 42,
):
    """Trains an SVM classifier using the best hyperparameters from tuning."""
    from mobile_price_classification import train_model as _train_model

    _train_model(
        train_x_path=train_x.path,
        train_y_path=train_y.path,
        fitted_scaler_path=fitted_scaler.path,
        hparams=hparams,
        trained_model_output_path=trained_model.path,
        seed=seed,
    )


@dsl.component(base_image=COMPONENTS_IMAGE)
def evaluate_model(
    val_x: Input[Dataset],
    val_y: Input[Dataset],
    fitted_scaler: Input[Artifact],
    trained_model: Input[Model],
    confusion_matrix_plot: Output[ClassificationMetrics],
    classification_report_md: Output[Markdown],
):
    """Evaluates the trained SVM model using validation data."""
    from mobile_price_classification import evaluate_model as _evaluate_model

    result = _evaluate_model(
        val_x_path=val_x.path,
        val_y_path=val_y.path,
        fitted_scaler_path=fitted_scaler.path,
        trained_model_path=trained_model.path,
        classification_report_output_path=classification_report_md.path,
    )

    confusion_matrix_plot.log_confusion_matrix(result["labels"], result["matrix"])


@dsl.component(base_image=COMPONENTS_IMAGE)
def test_model(
    test_x: Input[Dataset],
    trained_model: Input[Model],
    fitted_scaler: Input[Artifact],
    column_x: str,
    column_y: str,
    scatter_plot: Output[HTML],
):
    """Test a trained SVM model on test data and produce a scatter plot."""
    from mobile_price_classification import test_model as _test_model

    _test_model(
        test_x_path=test_x.path,
        trained_model_path=trained_model.path,
        fitted_scaler_path=fitted_scaler.path,
        column_x=column_x,
        column_y=column_y,
        scatter_plot_output_path=scatter_plot.path,
    )


@dsl.pipeline
def mobile_price_classification_pipeline(
    minio_train_data_path: str,
    minio_test_data_path: str,
    test_size: float = 0.5,
    C: List = [1, 0.1, 0.25, 0.5, 2, 0.75],
    kernel: List = ["linear", "rbf"],
    gamma: List = ["auto", 0.01, 0.001, 0.0001, 1],
    decision_function_shape: List[str] = ["ovo", "ovr"],
    scatter_plot_column_x: str = "ram",
    scatter_plot_column_y: str = "battery_power",
    seed: int = 42,
):
    """
    Mobile price classification pipeline using containerized components.

    This pipeline covers the following steps:
    1. Read data from the specified paths.
    2. Split the data into training and validation sets.
    3. Fit the MinMax scaler.
    4. Tune hyperparameters for the SVM model.
    5. Train the SVM model with the best hyperparameters.
    6. Evaluate the trained model.
    7. Test the model and visualize the results with a scatter plot.
    """
    from kfp import kubernetes

    # Step 1: Read the data
    read_data_task = read_data(
        minio_train_data_path=minio_train_data_path,
        minio_test_data_path=minio_test_data_path,
    )
    # Use the cluster internal s3 endpoint
    read_data_task.set_env_variable('AWS_ENDPOINT_URL',"http://minio.minio")
    # Use Kubernetes secrets to provide AWS credentials to the read_data component
    kubernetes.use_secret_as_env(
        read_data_task,
        secret_name='s3creds',
        secret_key_to_env={
            'AWS_ACCESS_KEY_ID': 'AWS_ACCESS_KEY_ID',
            'AWS_SECRET_ACCESS_KEY': 'AWS_SECRET_ACCESS_KEY',
        }
    ) 

    # Step 2: Split the data
    split_data_task = split_data(
        train_df=read_data_task.outputs["train_df"],
        test_size=test_size,
        seed=seed,
    )

    # Step 3: Fit the scaler
    fit_scaler_task = fit_scaler(train_x=split_data_task.outputs["x_train_df"])

    # Step 4: Tune hyperparameters
    tune_hyperparams_task = tune_hyperparams(
        train_x=split_data_task.outputs["x_train_df"],
        train_y=split_data_task.outputs["y_train_df"],
        fitted_scaler=fit_scaler_task.outputs["fitted_scaler"],
        C=C,
        kernel=kernel,
        gamma=gamma,
        decision_function_shape=decision_function_shape,
        seed=seed,
    )

    # Step 5: Train the model
    train_model_task = train_model(
        train_x=split_data_task.outputs["x_train_df"],
        train_y=split_data_task.outputs["y_train_df"],
        hparams=tune_hyperparams_task.output,
        fitted_scaler=fit_scaler_task.outputs["fitted_scaler"],
        seed=seed,
    )

    # Step 6: Evaluate the model
    evaluate_model_task = evaluate_model(
        val_x=split_data_task.outputs["x_val_df"],
        val_y=split_data_task.outputs["y_val_df"],
        trained_model=train_model_task.outputs["trained_model"],
        fitted_scaler=fit_scaler_task.outputs["fitted_scaler"],
    )

    # Step 7: Test the model and visualize
    test_model_task = test_model(
        test_x=read_data_task.outputs["test_df"],
        trained_model=train_model_task.outputs["trained_model"],
        fitted_scaler=fit_scaler_task.outputs["fitted_scaler"],
        column_x=scatter_plot_column_x,
        column_y=scatter_plot_column_y,
    )
