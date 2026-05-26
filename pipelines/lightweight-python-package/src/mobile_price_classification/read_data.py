import pandas as pd


def read_data(
    train_data_path: str,
    test_data_path: str,
    train_output_path: str,
    test_output_path: str,
):
    """
    Read training and test CSV data from object storage (or local paths) and save them as Parquet.

    When using S3-compatible object storage, access configuration is taken from environment variables such as
    AWS_ENDPOINT_URL, AWS_ACCESS_KEY_ID, and AWS_SECRET_ACCESS_KEY.
    """
    df_train = pd.read_csv(train_data_path)
    df_test = pd.read_csv(test_data_path)

    df_train.to_parquet(train_output_path)
    df_test.to_parquet(test_output_path)
