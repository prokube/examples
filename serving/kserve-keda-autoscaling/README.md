# KServe Autoscaling with KEDA and Custom Prometheus Metrics

This example demonstrates autoscaling a KServe InferenceService using
[KEDA](https://keda.sh/) with custom Prometheus metrics from vLLM.
It scales based on total token throughput rather than simple request count,
which is better suited for LLM inference workloads.

For full documentation, see the
[prokube autoscaling docs](https://docs.prokube.cloud/user_docs/model_serving_autoscaling/#keda-kubernetes-event-driven-autoscaling).

## Why Token Throughput?

LLM requests vary wildly in duration depending on prompt and output length.
Request-count metrics (concurrency, QPS) don't reflect actual GPU load.
Token throughput stays elevated as long as the model is under pressure,
making it a stable scaling signal.

## Prerequisites

- KEDA installed in the cluster (`helm install keda kedacore/keda -n keda --create-namespace`)
- Prometheus scraping vLLM metrics (prokube clusters include a cluster-wide PodMonitor)

## Files

| File | Description |
|------|-------------|
| `inference-service.yaml` | KServe InferenceService (OPT-125M, RawDeployment mode) |
| `scaled-object.yaml` | KEDA ScaledObject — scales on token throughput |

## Quick Start

> [!NOTE]
> All of the examples below should be run in prokube notebook's terminal inside your cluster. The model created with RawDeployment is not accessible from outside the cluster by default.

```bash
# 1. Deploy the InferenceService
kubectl apply -f inference-service.yaml

# 2. Wait for it to become ready
kubectl get isvc opt-125m -w

# 3. Deploy the KEDA ScaledObject (requires corresponding permissions)
kubectl apply -f scaled-object.yaml

# 4. Verify
kubectl get scaledobject
kubectl get hpa
```

## See It in Action

After deploying, you can trigger autoscaling and observe the full scale-up / scale-down cycle.

### 1. Send inference requests

Get the internal cluster address and send a request:

```bash
# inference service name + "-predictor"
SERVICE_URL=opt-125m-predictor

curl -s "$SERVICE_URL/openai/v1/completions" \
  -H "Content-Type: application/json" \
  -d '{"model":"opt-125m","prompt":"What is AI?","max_tokens":64}' \
  | python -c 'import json,sys;print("\n", json.load(sys.stdin)["choices"][0]["text"].strip(), "\n")'
```

### 2. Generate enough load to trigger scale-up

Run several concurrent workers (in the background!) to push token throughput above the threshold
(5 tokens/second per replica by default):

```bash
# 5 parallel workers, each sending requests in a loop
PIDS=""
for i in $(seq 1 5); do
  (while true; do
    curl -s "$SERVICE_URL/openai/v1/completions" \
      -H "Content-Type: application/json" \
      -d '{"model":"opt-125m","prompt":"Write a long story about a dragon","max_tokens":200}' > /dev/null
  done) &
  PIDS="$PIDS $!"
done

echo
echo "Load running (PIDs:$PIDS)"
echo "Stop with: kill$PIDS"
echo
```

### 3. Observe autoscaling

You can use dashboards (recommended, see below) or get a compact summary in terminal:

```bash
# polls every 10 seconds
watch -n10 '
echo "Deployment:"
kubectl get deployment opt-125m-predictor

echo
echo "Autoscaler:"
kubectl get hpa keda-hpa-opt-125m-scaledobject
'
```

**Grafana dashboards** (prokube clusters): to visualize token throughput and replica count over time, see:
- vLLM Performance Statistics: https://<YOUR_DOMAIN>/grafana/d/performance-statistics/vllm-performance-statistics
- vLLM Query Statistics: https://<YOUR_DOMAIN>/grafana/d/query-statistics4/vllm-query-statistics
- Replica count: https://<YOUR_DOMAIN>/grafana/d/demqj48/kubernetes-compute-resources-workload-copy

In our testing, the full cycle looked like:
1. **1 replica** at rest
2. Load applied (5 workers, ~55 tok/s total) — KEDA detects threshold breach
3. **Scaled to 3 replicas** within ~30 seconds
4. Load removed — metric drops to 0 — stabilization window (120s)
5. **Scaled back down** 3 → 2 → 1 gracefully (1 pod removed per minute)

## Customization

**Model name**: the `model_name="opt-125m"` filter in the Prometheus queries inside
`scaled-object.yaml` must match the `--model_name` argument in `inference-service.yaml`.

**Threshold**: the `threshold: "5"` value means "scale up when each replica
handles more than 5 tokens/second on average" (`AverageValue` divides the
query result by replica count). Tune this based on load testing for your
model and hardware.

**Multi-tenant clusters**: if multiple users may deploy models with the same
name, add a `namespace` filter to the Prometheus queries:

```promql
sum(rate(vllm:prompt_tokens_total{namespace="my-namespace",model_name="opt-125m"}[2m]))
```

**GPU deployments**: remove `--dtype=float32` and `--max-model-len=512`
from the InferenceService args, add GPU resource requests, and consider
adding a second trigger for GPU KV-cache utilization:

```yaml
# Add to scaled-object.yaml triggers list
- type: prometheus
  metadata:
    serverAddress: http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090/prometheus
    query: >-
      avg(vllm:gpu_cache_usage_perc{model_name="my-model"})
    metricType: AverageValue
    threshold: "0.75"
```

## References

- [prokube autoscaling documentation](https://docs.prokube.cloud/user_docs/model_serving_autoscaling/)
- [KServe KEDA autoscaler docs](https://kserve.github.io/website/docs/model-serving/predictive-inference/autoscaling/keda-autoscaler)
- [KEDA Prometheus scaler](https://keda.sh/docs/scalers/prometheus/)
- [vLLM metrics reference](https://docs.vllm.ai/en/latest/serving/metrics.html)
