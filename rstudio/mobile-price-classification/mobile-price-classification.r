library(tidyverse)
library(aws.s3)
library(readr)

# Add your bucket here (e.g. <workspace-name>-data)
bucket_name      <- ""
s3_key_train_csv <- "mobile-price-classification/train.csv"
s3_key_test_csv  <- "mobile-price-classification/test.csv"
endpoint         <- Sys.getenv("AWS_S3_ENDPOINT")

# Local temp paths for the download and unzip.
zip_path   <- tempfile(fileext = ".zip")
unzip_dir  <- tempfile("mobile_price_")

# Kaggle requires API credentials via env vars KAGGLE_USERNAME and KAGGLE_KEY.
# The dataset link: https://www.kaggle.com/datasets/iabhishekofficial/mobile-price-classification
download.file(
  url      = "https://www.kaggle.com/api/v1/datasets/download/iabhishekofficial/mobile-price-classification",
  destfile = zip_path,
  mode     = "wb"
)

unzip(zip_path, exdir = unzip_dir)

train_path <- file.path(unzip_dir, "train.csv")
test_path  <- file.path(unzip_dir, "test.csv")

# Optional: push the CSVs to S3/MinIO so you can reuse them from there later.
# Safe the s3 config.
s3_cfg <- list(use_https = FALSE, region = "", use_path_style = TRUE)

if (!bucket_exists(bucket_name, base_url = endpoint, use_https = s3_cfg$use_https, region = s3_cfg$region)) {
  put_bucket(bucket_name, use_https = s3_cfg$use_https, region = s3_cfg$region)
}

put_object(file = train_path, object = s3_key_train_csv, bucket = bucket_name,
           use_https = s3_cfg$use_https, region = s3_cfg$region)
put_object(file = test_path, object = s3_key_test_csv, bucket = bucket_name,
           use_https = s3_cfg$use_https, region = s3_cfg$region)

# Load the training data into a tibble.
train_df <- read_csv(train_path, show_col_types = FALSE)
test_df  <- read_csv(test_path, show_col_types = FALSE)

# Train/validation split (80/20) using base R sampling.
set.seed(42)
idx <- sample(nrow(train_df), size = 0.8 * nrow(train_df))
train_split <- train_df[idx, ]
valid_split <- train_df[-idx, ]

# --- Visualizations ---


# 1) Class balance for price_range.
ggplot(train_df, aes(x = factor(price_range))) +
  geom_bar(fill = "steelblue") +
  labs(title = "Price range distribution", x = "price_range", y = "count") +
  theme_minimal()

# 2) RAM vs price_range as boxplots.
ggplot(train_df, aes(x = factor(price_range), y = ram)) +
  geom_boxplot(fill = "tan") +
  labs(title = "RAM by price range", x = "price_range", y = "RAM (MB)") +
  theme_minimal()

# 3) Battery power histogram colored by price_range.
ggplot(train_df, aes(x = battery_power, fill = factor(price_range))) +
  geom_histogram(position = "identity", alpha = 0.4, bins = 30) +
  labs(title = "Battery power distribution", x = "battery_power (mAh)", fill = "price_range") +
  theme_minimal()


