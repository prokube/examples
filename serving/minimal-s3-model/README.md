# Minimal KServe + MinIO Model Serving Example

This example demonstrates end-to-end model serving on prokube from a MinIO bucket: training a simple sklearn model,
uploading it to MinIO, deploying it as a KServe InferenceService, and testing it with a prediction request.

**Requires prokube platform v1.7.0+.** To check your version, run the following in your notebook:

```py
!kubectl get cm -n prokube paas-version -o jsonpath='{.data.paasVersion}'
```

## What the notebook does

1. Trains a small SVM classifier on the Iris dataset and serializes it with `joblib`.
2. Uploads the model to your MinIO bucket using `s3fs`.
3. Generates and deploys a KServe `InferenceService` manifest via `kubectl`.
4. Tests the deployed service using both the internal cluster URL and the external URL.
