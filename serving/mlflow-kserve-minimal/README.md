# Minimal MLflow Model Inference

This directory shows how to deploy an MLflow-tracked model as a KServe
InferenceService using the v2 inference protocol. It uses the built-in
`mlflow` model format in KServe, so no custom container image is required.

## Prerequisites

- A model trained and registered in MLflow. See the
  [mobile price classification MLflow example](../../mlflow/mobile-price-classification/)
  for how to train and register the SVM model used here.
- `kubectl` access to your prokube namespace. (already installed in a pk-notebook)
- Python with the `requests` package installed (for testing, already installed in a pk-notebook)

## Deploy the InferenceService

1. Open `InferenceService.yaml` and replace the placeholder values:

   | Placeholder | Description |
   |---|---|
   | `<inference-name>` | A name for your InferenceService (e.g. `mobile-price-svm`) |
   | `<workspace-name>` | Your Kubeflow namespace / workspace |
   | `<your-user>` | Your username, matching the model name registered in MLflow |

   You can also adjust the model version number at the end of the `storageUri`
   (e.g. `/2` refers to version 2 of the registered model).

   The `storageUri` uses the `mlflow://` scheme, which tells KServe to fetch
   the model artifact directly from the MLflow model registry.

   > [!WARNING]
   > You need to the a MLFlow ClusterStorageContainer in order to use the
   > `mlflow://` scheme (prokube platform versions >= 1.7.0)

2. Apply the manifest:
   ```sh
   kubectl apply -f InferenceService.yaml -n <your-namespace>
   ```

3. Wait for the InferenceService to become ready. You can check the status in
   the Kubeflow Endpoints UI or via:
   ```sh
   kubectl get inferenceservice -n <your-namespace>
   ```

## Test the Deployment

A test script and sample request body are provided to verify the deployment.

1. Set the required environment variables (optional):
   ```sh
   export API_KEY=<your-api-key>
   export INFERENCE_SERVICE_URI=<your-inference-service-url>
   export PROTOCOL_VERSION=v2
   ```
   You can find the inference service URL in the Kubeflow Endpoints UI. If you
   don't know your API key, reach out to your prokube admin.

2. Run the test script:
   ```sh
   python test_inference_service.py \
     --model <inference-name> \
     --json v2-mlflow-inference-body.json
   ```

   The script sends the sample request to the deployed model and prints the
   response.

   If `API_KEY` or `INFERENCE_SERVICE_URI` are not set as environment
   variables, the script will prompt you for them interactively.

## Request Body Format

The provided `v2-mlflow-inference-body.json` follows the
[v2 inference protocol](https://kserve.github.io/website/latest/modelserving/data_plane/v2_protocol/).
Each feature is specified as a separate input with a name, shape, datatype, and
data array. The sample contains 5 data points across 20 features from the
mobile price classification dataset.

The test script also supports the v1 protocol. To use it, set
`PROTOCOL_VERSION=v1` and provide a v1-formatted request body.
