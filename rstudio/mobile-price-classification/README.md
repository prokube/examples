# Mobile Price Classification Workflow

This project demonstrates a technical workflow in R for handling the Kaggle Mobile Price Classification dataset. It is intended purely as a demonstration of basic data processing, storage, and simple data visualization in RStudio—not as a data science tutorial or analysis. No data science background is required.

**Note:** Kaggle credentials are not required to run this script. All necessary tools and environment settings are pre-configured in the RStudio image.

The included `mobile-price-classification.r` script performs the following steps:

1. **Download Dataset from Kaggle:**
   - Automatically downloads the Mobile Price Classification dataset directly from Kaggle. No manual credential setup is needed.

2. **Unzip Dataset:**
   - Extracts the downloaded zip file into a local temporary directory.

3. **Upload to S3/MinIO:**
   - Optionally uploads the extracted CSV files (`train.csv`, `test.csv`) to a specified S3 or MinIO bucket for reuse.
   - Requires appropriate S3 endpoint and bucket configuration (already set up in the RStudio environment).

4. **Load Data:**
   - Loads the training and test data into R tibbles for further demonstration.

5. **Train/Validation Split:**
   - Splits the training data into train/validation sets (80/20 split); no modeling or analysis is performed.

6. **Exploratory Visualizations:**
   - Generates basic plots to illustrate class balance and feature relationships.

