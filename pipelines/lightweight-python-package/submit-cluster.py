import datetime
from kfp.client import Client
from pipeline import mobile_price_classification_pipeline


if __name__ == "__main__":
    with open(
        "/var/run/secrets/kubernetes.io/serviceaccount/namespace", "r", encoding="utf-8"
    ) as namespace_file:
        namespace = namespace_file.read().strip()

    s3_bucket = f"{namespace}-data"
    s3_dataset_path = f"{s3_bucket}/mobile-price-classification"

    client = Client()

    run = client.create_run_from_pipeline_func(
        mobile_price_classification_pipeline,
        enable_caching=True,
        arguments={
            "train_data_path": f"s3://{s3_dataset_path}/train.csv",
            "test_data_path": f"s3://{s3_dataset_path}/test.csv",
            "test_size": 0.2,
            "C": [1, 0.1, 0.25, 0.5, 2, 0.75],
            "kernel": ["linear", "rbf"],
            "gamma": ["auto", 0.01, 0.001, 0.0001, 1],
            "decision_function_shape": ["ovo", "ovr"],
            "scatter_plot_column_x": "ram",
            "scatter_plot_column_y": "battery_power",
            "seed": 42,
        },
        experiment_name="mobile-price-classification-containerized",
        run_name=f"Containerized pipeline {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    )
    print(f"KFP_RUN_ID={run.run_id}")
