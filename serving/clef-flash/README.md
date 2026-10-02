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

## Model download

The public snapshot is pinned to the revision in the table. The Job resumes
partial downloads, verifies `joint_head.safetensors` and
`joint_schema_model.py`, and writes `.model-revision` only after both files
exist. Serving restarts mount the completed `clef-flash` directory from the
PVC at `/mnt/models` and do not download weights again.

## Install and serve

Install the runtime, model volume and download Job, and H200 service as one
Helm release in the target namespace:

```sh
NAMESPACE="your-namespace"

helm upgrade --install clef-flash . \
  --namespace "${NAMESPACE}"
kubectl logs -n "${NAMESPACE}" -f job/download-clef-flash
kubectl wait -n "${NAMESPACE}" --for=condition=complete \
  job/download-clef-flash --timeout=45m
kubectl wait -n "${NAMESPACE}" --for=condition=Ready \
  inferenceservice/clef-flash --timeout=30m
```

The dedicated `clef` model format and explicit `runtime` field prevent KServe
from selecting a generic Hugging Face runtime. Liveness remains healthy while
the model loads and fails if initialization terminates with an error; readiness
remains unavailable until loading succeeds.

The release also runs the Tetris UI as a small unprivileged nginx deployment.
Its same-origin `/v1/systemone` proxy calls the predictor through cluster DNS,
so browsers need neither CORS exceptions nor model credentials. Configure the
public Kubeflow route through `ui.host`, `ui.gateway`, and `ui.path`:

```sh
helm upgrade clef-flash . --namespace "${NAMESPACE}" \
  --set ui.enabled=true
```

By default, users can switch between the decision model and the local
heuristic. Set `ui.policy` to `clef` or `heuristic` to lock the deployment to
one policy and hide the policy control.

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
| Cold startup to Ready | 91 seconds, including image pull |
| Idle GPU memory | 19,010 MiB |
| Peak GPU memory during smoke test | Not measured |

## Monitoring

When Prometheus Operator CRDs are installed, enable the bundled `PodMonitor`
and Grafana dashboard:

```sh
helm upgrade clef-flash . --namespace "${NAMESPACE}" \
  --set monitoring.enabled=true
```

The monitor scrapes only the runtime's bounded-cardinality `clef_*` metrics.
The dashboard combines model readiness and loading, request outcomes and
latency, in-flight requests, and the platform DCGM framebuffer metrics. Its
ConfigMap uses `grafana_dashboard=1` and is created in the release namespace by
default. Set `monitoring.dashboardNamespace` only when the Grafana sidecar is
restricted to another namespace and Helm is authorized to write there.

To release the GPU without uninstalling the UI and monitoring resources, set
`inferenceService.minReplicas=0` and `inferenceService.stopped=true`. Restore
the defaults to serve the model again.

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
helm uninstall clef-flash --namespace "${NAMESPACE}"
```

Deleting the PVC permanently removes the downloaded snapshot.

## References

- [CLEF-Flash model card](https://huggingface.co/Cloudflare/clef-flash)
- [SystemOne runtime details](server/README.md)
