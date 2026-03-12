import pandas as pd


def read_data(
    minio_train_data_path: str,
    minio_test_data_path: str,
    train_output_path: str,
    test_output_path: str,
):
    df_train = pd.read_csv(minio_train_data_path)
    df_test = pd.read_csv(minio_test_data_path)

    df_train.to_parquet(train_output_path)
    df_test.to_parquet(test_output_path)
