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

```bash
export NAMESPACE="default"

# 1. Deploy the InferenceService
kubectl apply -n $NAMESPACE -f inference-service.yaml

# 2. Wait for it to become ready
kubectl get isvc opt-125m -n $NAMESPACE -w

# 3. Deploy the KEDA ScaledObject
kubectl apply -n $NAMESPACE -f scaled-object.yaml

# 4. Verify
kubectl get scaledobject -n $NAMESPACE
kubectl get hpa -n $NAMESPACE
```

## Customization

**Namespace and model name**: replace `default` and `opt-125m` in the
Prometheus queries inside `scaled-object.yaml`.

**Threshold**: the `threshold: "5"` value means "scale up when each replica
handles more than 5 tokens/second on average" (`AverageValue` divides the
query result by replica count). Tune this based on load testing for your
model and hardware.

**GPU deployments**: remove `--dtype=float32` and `--max-model-len=512`
from the InferenceService args, add GPU resource requests, and consider
adding a second trigger for GPU KV-cache utilization:

```yaml
# Add to scaled-object.yaml triggers list
- type: prometheus
  metadata:
    serverAddress: http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090/prometheus
    query: >-
      avg(vllm:gpu_cache_usage_perc{namespace="my-namespace",model_name="my-model"})
    metricType: AverageValue
    threshold: "0.75"
```

## References

- [prokube autoscaling documentation](https://docs.prokube.cloud/user_docs/model_serving_autoscaling/)
- [KServe KEDA autoscaler docs](https://kserve.github.io/website/docs/model-serving/predictive-inference/autoscaling/keda-autoscaler)
- [KEDA Prometheus scaler](https://keda.sh/docs/scalers/prometheus/)
- [vLLM metrics reference](https://docs.vllm.ai/en/latest/serving/metrics.html)
