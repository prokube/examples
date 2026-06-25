# Shiny Iris Dashboard

This example demonstrates how to build and run an interactive Shiny application from an RStudio environment on Kubeflow. It uses the built-in Iris dataset, so no external downloads, API credentials, or object storage configuration are required.

**Libraries used:** `shiny`, `ggplot2`, `dplyr`

The included `app.R` application demonstrates the following Shiny capabilities:

1. **Reactive Filtering:**
   - Filter the Iris dataset by species, petal length, and sepal length.

2. **Interactive Visualization:**
   - Choose the x/y variables for a scatter plot.
   - Toggle an optional trend line.
   - See plots update immediately when controls change.

3. **Reactive Summaries:**
   - View grouped summary statistics for the currently filtered data.

4. **Interactive Data Table:**
   - Browse, sort, and search the filtered records.

5. **Download Filtered Data:**
   - Export the currently selected rows as a CSV file.

6. **Live Prediction Panel:**
   - Enter flower measurements and classify them with a lightweight nearest-centroid classifier.
   - Visualize the prediction against the original observations and species centroids.

## Running the App

Open `app.R` in RStudio and click **Run App**, or run:

```r
install.packages(c("shiny", "ggplot2", "dplyr"))
shiny::runApp("app.R", host = "0.0.0.0", port = 3838)
```

If you are already in the `shiny-iris-dashboard` directory, this shorter command is enough:

```r
shiny::runApp(host = "0.0.0.0", port = 3838)
```

## Notes

- The app is intentionally self-contained and uses only data bundled with R.
- This example is focused on running Shiny interactively from RStudio. A containerized Shiny deployment can be added separately if the app should be exposed as a standalone Kubeflow/Istio service.
