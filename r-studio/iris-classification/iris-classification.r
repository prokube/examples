library(tidyverse)
library(aws.s3)

# Install non standard libraries
install.packages('caret')
install.packages('corrplot')

library(caret)
library(corrplot)

# ==============================================================================
# 1. Load and Prepare Data
# ==============================================================================

# The Iris dataset is built into R — no download needed.
iris_df <- as_tibble(iris)

# Quick look at the data.
cat("Dataset dimensions:", nrow(iris_df), "x", ncol(iris_df), "\n")
glimpse(iris_df)
summary(iris_df)

# ==============================================================================
# 2. Upload to S3/MinIO
# ==============================================================================

# Add your bucket here (e.g. <workspace-name>-data)
bucket_name  <- ""
s3_key_csv   <- "iris-classification/iris.csv"
endpoint     <- Sys.getenv("AWS_S3_ENDPOINT")

# Write data to a temp CSV for upload.
csv_path <- tempfile(fileext = ".csv")
write_csv(iris_df, csv_path)

# S3 config for MinIO (HTTP, path-style, no region).
s3_cfg <- list(use_https = FALSE, region = "", use_path_style = TRUE)

if (!bucket_exists(bucket_name, base_url = endpoint,
                   use_https = s3_cfg$use_https, region = s3_cfg$region)) {
  put_bucket(bucket_name, use_https = s3_cfg$use_https, region = s3_cfg$region)
}

put_object(file = csv_path, object = s3_key_csv, bucket = bucket_name,
           use_https = s3_cfg$use_https, region = s3_cfg$region)

cat("Uploaded iris.csv to bucket:", bucket_name, "\n")

# ==============================================================================
# 3. Exploratory Data Analysis
# ==============================================================================

# 3a) Class distribution.
ggplot(iris_df, aes(x = Species, fill = Species)) +
  geom_bar() +
  labs(title = "Species Distribution", x = "Species", y = "Count") +
  theme_minimal() +
  theme(legend.position = "none")

# 3b) Correlation heatmap of numeric features.
cor_matrix <- cor(iris_df %>% select(where(is.numeric)))
corrplot(cor_matrix, method = "color", type = "upper",
         addCoef.col = "black", tl.col = "black",
         title = "Feature Correlation Matrix",
         mar = c(0, 0, 2, 0))

# 3c) Petal dimensions by species.
ggplot(iris_df, aes(x = Petal.Length, y = Petal.Width, color = Species)) +
  geom_point(size = 2, alpha = 0.7) +
  labs(title = "Petal Length vs Width by Species",
       x = "Petal Length (cm)", y = "Petal Width (cm)") +
  theme_minimal()

# 3d) Sepal dimensions by species.
ggplot(iris_df, aes(x = Sepal.Length, y = Sepal.Width, color = Species)) +
  geom_point(size = 2, alpha = 0.7) +
  labs(title = "Sepal Length vs Width by Species",
       x = "Sepal Length (cm)", y = "Sepal Width (cm)") +
  theme_minimal()

# 3e) Feature distributions as boxplots.
iris_long <- iris_df %>%
  pivot_longer(cols = -Species, names_to = "Feature", values_to = "Value")

ggplot(iris_long, aes(x = Species, y = Value, fill = Species)) +
  geom_boxplot() +
  facet_wrap(~Feature, scales = "free_y") +
  labs(title = "Feature Distributions by Species") +
  theme_minimal() +
  theme(legend.position = "none")

# ==============================================================================
# 4. Train/Test Split
# ==============================================================================

set.seed(42)
train_idx   <- createDataPartition(iris_df$Species, p = 0.8, list = FALSE)
train_split <- iris_df[train_idx, ]
test_split  <- iris_df[-train_idx, ]

cat("Training set:", nrow(train_split), "rows\n")
cat("Test set:    ", nrow(test_split), "rows\n")

# ==============================================================================
# 5. Model Training — Random Forest with 5-fold CV
# ==============================================================================

ctrl <- trainControl(method = "cv", number = 5)

rf_model <- train(
  Species ~ .,
  data      = train_split,
  method    = "rf",
  trControl = ctrl,
  tuneLength = 3
)

print(rf_model)

# ==============================================================================
# 6. Model Evaluation
# ==============================================================================

# Predict on the test set.
predictions <- predict(rf_model, newdata = test_split)

# Confusion matrix and detailed metrics.
cm <- confusionMatrix(predictions, test_split$Species)
print(cm)

cat("\nOverall Accuracy:", round(cm$overall["Accuracy"] * 100, 1), "%\n")

# 6a) Feature importance plot.
importance_df <- varImp(rf_model)$importance %>%
  rownames_to_column("Feature") %>%
  pivot_longer(-Feature, names_to = "Class", values_to = "Importance")

ggplot(importance_df, aes(x = reorder(Feature, Importance), y = Importance, fill = Class)) +
  geom_col(position = "dodge") +
  coord_flip() +
  labs(title = "Feature Importance (Random Forest)",
       x = "Feature", y = "Importance") +
  theme_minimal()

# 6b) Prediction results — actual vs predicted.
results_df <- test_split %>%
  mutate(Predicted = predictions, Correct = Species == Predicted)

ggplot(results_df, aes(x = Petal.Length, y = Petal.Width,
                       color = Predicted, shape = Correct)) +
  geom_point(size = 3, alpha = 0.8) +
  scale_shape_manual(values = c("TRUE" = 16, "FALSE" = 4)) +
  labs(title = "Test Set Predictions",
       subtitle = "X marks misclassifications",
       x = "Petal Length (cm)", y = "Petal Width (cm)") +
  theme_minimal()


