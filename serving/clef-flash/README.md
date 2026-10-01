# CLEF-Flash on KServe

This example downloads
[`Cloudflare/clef-flash`](https://huggingface.co/Cloudflare/clef-flash)
once to persistent storage and serves its SystemOne decision head with the
custom FastAPI runtime in [`server/`](server/). It does not use KServe's
generic Hugging Face runtime.

## Deployment profile

The initial profile follows the upstream single-H200 test configuration and
serves one request at a time:

| Setting | Value |
|---|---|
| Model revision | `17f0b0ad64efb65d273590632833508766b2aae6` |
| Model size | About 19 GB of BF16 weights |
| GPU resource | `nvidia.com/mig-7g.141gb: 1` |
| Node selector | `nvidia.com/gpu.product: NVIDIA-H200-NVL` |
| CPU | 8 requested, 16 limited |
| Memory | 32 GiB requested, 64 GiB limited |
| Shared memory | 16 GiB memory-backed `/dev/shm` |
| Request concurrency | 1 |
| Model readiness wait | 30 minutes |

The H200 selector and full-size MIG resource match the current prokube.ai H200
nodes. Change both fields together if the target cluster exposes a full H200
as `nvidia.com/gpu` or uses another product label. Do not use a smaller MIG
profile for the 19 GB model without measuring model and activation memory.

The runtime manifest pins the published `clef-systemone` image by immutable
digest. Rebuilds through `.github/workflows/build-images.yaml` must update that
digest explicitly; deployments never follow a mutable tag.

## Prerequisites

- KServe with raw PVC model storage enabled
- NVIDIA GPU Operator and a full-size H200 MIG device
- A default StorageClass that can provision a 30 GiB `ReadWriteOnce` PVC
- Cluster-wide permission to create a `ClusterServingRuntime`
- `curl`, `jq`, and `kubectl` for the smoke test

The download Job uses the same H200 node selector as the service so a local or
zonal `WaitForFirstConsumer` volume binds in the correct topology. It does not
request the GPU. Change both manifests together if the cluster's H200 product
label differs.

## Download the exact model revision

Create the PVC and one-time download Job in the serving namespace:

```sh
NAMESPACE="your-namespace"

kubectl create -n "${NAMESPACE}" -f model-pvc.yaml
kubectl create -n "${NAMESPACE}" -f download-model-job.yaml
kubectl logs -n "${NAMESPACE}" -f job/download-clef-flash
kubectl wait -n "${NAMESPACE}" --for=condition=complete \
  job/download-clef-flash --timeout=45m
```

The public snapshot is pinned to the revision in the table. The Job resumes
partial downloads, verifies `joint_head.safetensors` and
`joint_schema_model.py`, and writes `.model-revision` only after both files
exist. Serving restarts mount the completed `clef-flash` directory from the
PVC at `/mnt/models` and do not download weights again.

## Install and serve

Create the cluster-scoped runtime once and the H200 service in the target
namespace:

```sh
kubectl create -f cluster-serving-runtime.yaml
kubectl create -n "${NAMESPACE}" -f inference-service-h200.yaml
kubectl wait -n "${NAMESPACE}" --for=condition=Ready \
  inferenceservice/clef-flash --timeout=30m
```

The dedicated `clef` model format and explicit `runtime` field prevent KServe
from selecting a generic Hugging Face runtime. Liveness remains healthy while
the model loads and fails if initialization terminates with an error; readiness
remains unavailable until loading succeeds.

Inspect placement, startup duration, and GPU memory before smoke testing:

```sh
kubectl get pods -n "${NAMESPACE}" \
  -l serving.kserve.io/inferenceservice=clef-flash -o wide
kubectl logs -n "${NAMESPACE}" \
  -l serving.kserve.io/inferenceservice=clef-flash \
  -c kserve-container --prefix
```

Use the cluster's DCGM `DCGM_FI_DEV_FB_USED` metric or `nvidia-smi` on the
selected node to collect GPU memory. Record the measured values here after the
first deployment:

| Measurement | H200 result |
|---|---:|
| Cold startup to Ready | Not measured; deployment cluster unavailable |
| Idle GPU memory | Not measured; deployment cluster unavailable |
| Peak GPU memory during smoke test | Not measured; deployment cluster unavailable |

## Smoke test

The script reads the public URL from `.status.url` and, when the Agent Gateway
Service exists, converts its `/serving/` route to the external
`/svc/serving/` form. An explicitly supplied `API_BASE` is used unchanged. The
script submits one request containing choice, score, and noul questions and
validates all three answer shapes and probability distributions.
`API_KEY` takes precedence over the CI-standard
`INFERENCE_SERVICE_API_KEY` environment variable.

```sh
NAMESPACE="${NAMESPACE}" INFERENCE_SERVICE_API_KEY="your-x-api-key" ./smoke-test.sh
```

For an unauthenticated port-forward, set `API_BASE` to the forwarded base URL
and omit `API_KEY`.

## Cleanup

```sh
kubectl delete -n "${NAMESPACE}" inferenceservice clef-flash --ignore-not-found
kubectl delete -n "${NAMESPACE}" job download-clef-flash --ignore-not-found
kubectl delete -n "${NAMESPACE}" pvc clef-flash-model --ignore-not-found
kubectl delete clusterservingruntime clef-flash-systemone --ignore-not-found
```

Deleting the PVC permanently removes the downloaded snapshot.

## References

- [CLEF-Flash model card](https://huggingface.co/Cloudflare/clef-flash)
- [SystemOne runtime details](server/README.md)
