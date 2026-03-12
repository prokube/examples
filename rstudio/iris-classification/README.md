# Iris Classification Workflow

This project demonstrates a complete data science workflow in R using the classic Iris dataset. It covers data exploration, visualization, model training, and evaluation — all within an RStudio environment on Kubeflow.

**Libraries used:** `tidyverse`, `aws.s3`, `caret`, `corrplot`

No external downloads or API credentials are required. The Iris dataset is built into R.

The included `iris-classification.r` script performs the following steps:

1. **Load and Prepare Data:**
   - Loads the built-in Iris dataset and converts it to a tibble for tidy processing.

2. **Upload to S3/MinIO:**
   - Exports the dataset as CSV and uploads it to an S3-compatible bucket for persistence and reuse.

3. **Exploratory Data Analysis (EDA):**
   - Summary statistics, class distribution, and feature distributions by species.
   - Correlation heatmap of numeric features.
   - Scatter plots showing petal and sepal relationships colored by species.

4. **Train/Test Split:**
   - Splits the data 80/20 with stratified sampling to preserve class balance.

5. **Model Training:**
   - Trains a Random Forest classifier using `caret` with 5-fold cross-validation.

6. **Model Evaluation:**
   - Generates predictions on the test set.
   - Prints a confusion matrix with accuracy, precision, recall, and F1 metrics.
   - Visualizes feature importance and prediction results.
