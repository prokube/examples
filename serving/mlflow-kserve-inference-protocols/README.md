# MLflow KServe Inference Protocols

This directory demonstrates both the v1 and v2 inference protocols for
MLflow-tracked models deployed as KServe InferenceServices on prokube.

It uses two ISVCs side-by-side:

| ISVC | Model format | Protocol | YAML |
|---|---|---|---|
| `v1-mobile-price-classification-inference` | `sklearn` | v1 | `v1-InferenceService.yaml` |
| `v2-mobile-price-classification-inference` | `mlflow` | v2 | `v2-InferenceService.yaml` |

The notebook `inference_protocol_version_example.ipynb` walks through deploying
both and comparing request/response shapes for each protocol.

## Prerequisites

- A model trained and registered in MLflow. See the
  [mobile price classification MLflow example](../../mlflow/mobile-price-classification/)
  for how to train and register the SVM model used here.
- `kubectl` access to your prokube namespace. (already installed in a pk-notebook)
- Python with the `requests` package installed (for testing, already installed in a pk-notebook)

## Why a dedicated ServiceAccount is required

> [!IMPORTANT]
> MLflow ISVCs **must** use the dedicated `mlflow-isvc-sa` ServiceAccount
> defined in `ServiceAccount.yaml`. Do not use the namespace `default` SA.

### Root cause: KServe S3 credential injection conflict

KServe v0.18.0 automatically injects S3 credentials into the
`storage-initializer` init container for every ISVC whose ServiceAccount
references a secret annotated as an S3 credential source (e.g. the
`s3creds` secret present in every prokube namespace).

The injection produces two kinds of env entries for the same variable names
(`S3_ENDPOINT`, `AWS_ENDPOINT_URL`, `S3_USE_HTTPS`, etc.):

| Source | Env form |
|---|---|
| Secret annotations (`serving.kserve.io/s3-endpoint`, `s3-usehttps`, …) | `value: <literal>` |
| Secret keys (mounted via `valueFrom.secretKeyRef`) | `valueFrom: {secretKeyRef: …}` |

Kubernetes rejects a container spec that sets **both** `value` and
`valueFrom` on the same env var. The admission webhook blocks the pod, the
storage-initializer never runs, and the ISVC times out with
`timed out waiting for condition`.

This only affects `mlflow://` ISVCs: S3-backed ISVCs (`s3://`) rely on
exactly that injection and work correctly with the `default` SA.

### The fix

`ServiceAccount.yaml` defines `mlflow-isvc-sa`, a dedicated SA that:

- Holds the `regcred-prokube` and `regcred-dev` imagePullSecrets so that
  the private prokube storage-initializer image can be pulled.
- Does **not** reference `s3creds`, so KServe skips S3 credential injection
  entirely for any ISVC that uses it.

Both `v1-InferenceService.yaml` and `v2-InferenceService.yaml` already
reference this SA.

## API key

> [!TIP]
> `apply.py` (and the notebook's `deploy()` call) need a model-serving API
> key. Ask your cluster administrator for one, or use pkui if it is
> available on your platform. Set `API_KEY` in the environment before
> calling `apply.py`, or you'll be prompted for it interactively.

## Deploy

1. Apply the ServiceAccount (once per namespace):

   ```sh
   kubectl apply -f ServiceAccount.yaml
   ```

2. Replace the placeholder values in both ISVC YAMLs:

   | Placeholder | Description |
   |---|---|
   | `<workspace-name>` | Your Kubeflow namespace / workspace |
   | `<username>` | Your username, matching the model registered in MLflow |

3. Apply both ISVCs:

   ```sh
   kubectl apply -f v1-InferenceService.yaml -n <your-namespace>
   kubectl apply -f v2-InferenceService.yaml -n <your-namespace>
   ```

4. Wait for both to become ready:

   ```sh
   kubectl get inferenceservice -n <your-namespace>
   ```

   > [!WARNING]
   > You need a MLFlow ClusterStorageContainer in order to use the
   > `mlflow://` scheme (prokube platform versions >= 1.7.0)

## Cleanup

To delete both ISVCs:

```sh
python cleanup.py
```

Or with `--dry-run` to preview the commands:

```sh
python cleanup.py --dry-run
```
