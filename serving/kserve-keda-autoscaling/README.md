# KServe Autoscaling with KEDA and Custom Metrics

This example demonstrates how to autoscale KServe InferenceServices using [KEDA](https://keda.sh/) with custom Prometheus metrics. This is particularly useful for LLM inference workloads where request-based autoscaling (Knative default) is not optimal.

## Why Custom Metrics for LLM Autoscaling?

Traditional request-based autoscaling doesn't work well for LLM inference because:

- **Token-level work**: LLM inference operates at token level, not request level. A single request can generate hundreds of tokens.
- **Variable latency**: Request latency varies significantly based on input/output token count.
- **Memory pressure**: LLM models require significant GPU memory (KV cache), which fills up based on concurrent requests.

Better metrics for LLM autoscaling include:
- **Time To First Token (TTFT)**: Latency until first token is generated
- **KV Cache utilization**: GPU memory used for attention cache
- **Number of running/waiting requests**: Queue depth

## Prerequisites

On prokube, Prometheus is already installed. You only need to install KEDA:

```bash
helm repo add kedacore https://kedacore.github.io/charts
helm install keda kedacore/keda --namespace keda --create-namespace
```

## Files

| File | Description |
|------|-------------|
| `inference-service.yaml` | KServe InferenceService for OPT-125M model with vLLM backend |
| `scaled-object.yaml` | KEDA ScaledObject with TTFT, GPU cache, and request-based scaling |
| `service-monitor.yaml` | PodMonitor and PrometheusRules for vLLM metrics collection |

## Deployment

### 1. Deploy the InferenceService

```bash
kubectl apply -f inference-service.yaml -n <your-namespace>
```

Wait for the model to be ready:
```bash
kubectl get inferenceservice opt-125m-vllm -n <your-namespace> -w
```

### 2. Configure Prometheus Metrics Collection

Apply the PodMonitor to scrape vLLM metrics:
```bash
kubectl apply -f service-monitor.yaml -n <your-namespace>
```

**Note:** You may need to update the `namespaceSelector` in `service-monitor.yaml` to match your namespace.

### 3. Deploy KEDA ScaledObject

First, identify the correct deployment name:
```bash
kubectl get deployments -n <your-namespace> | grep opt-125m-vllm
```

Update `scaled-object.yaml` with:
- The correct deployment name
- Your namespace in the Prometheus queries

Then apply:
```bash
kubectl apply -f scaled-object.yaml -n <your-namespace>
```

Verify the ScaledObject:
```bash
kubectl get scaledobject -n <your-namespace>
kubectl describe scaledobject opt-125m-vllm-scaledobject -n <your-namespace>
```

## Autoscaling Strategies

This example uses three triggers (first one to exceed threshold wins):

### 1. Time To First Token (TTFT) - P95
Scales when the 95th percentile TTFT exceeds 200ms:
```yaml
triggers:
  - type: prometheus
    metadata:
      query: |
        histogram_quantile(0.95, sum(rate({"__name__"="vllm:time_to_first_token_seconds_bucket", namespace="<your-namespace>"}[2m])) by (le))
      threshold: "0.2"
```

### 2. GPU KV-Cache Utilization
Scales when GPU cache usage exceeds 70% (for GPU deployments):
```yaml
triggers:
  - type: prometheus
    metadata:
      query: |
        avg({"__name__"="vllm:gpu_cache_usage_perc", namespace="<your-namespace>"})
      threshold: "0.7"
```

### 3. Running Requests (Fallback)
Scales when average running requests per pod exceeds 2:
```yaml
triggers:
  - type: prometheus
    metadata:
      query: |
        avg({"__name__"="vllm:num_requests_running", namespace="<your-namespace>"})
      threshold: "2"
```

## vLLM Metrics Reference

vLLM exposes metrics at `/metrics` endpoint. Note that vLLM uses colons in metric names:

| Metric | Description |
|--------|-------------|
| `vllm:num_requests_running` | Number of requests currently being processed |
| `vllm:num_requests_waiting` | Number of requests waiting in queue |
| `vllm:gpu_cache_usage_perc` | GPU KV cache utilization (0-1) |
| `vllm:time_to_first_token_seconds` | Histogram of TTFT |
| `vllm:time_per_output_token_seconds` | Histogram of TPOT |
| `vllm:generation_tokens_total` | Total number of generated tokens |

## Testing Autoscaling

Generate load to trigger autoscaling:

```bash
# Create a load generator pod
kubectl run load-gen --image=curlimages/curl -n <your-namespace> --restart=Never -- \
  sh -c 'while true; do for i in $(seq 1 10); do curl -s -X POST "http://opt-125m-vllm-predictor-00001.<your-namespace>.svc.cluster.local/openai/v1/completions" -H "Content-Type: application/json" -d "{\"model\": \"opt-125m\", \"prompt\": \"Tell me a story\", \"max_tokens\": 200}" & done; sleep 2; done'
```

Monitor scaling:
```bash
# Watch HPA status
kubectl get hpa -n <your-namespace> -w

# Watch pods
kubectl get pods -n <your-namespace> -l serving.kserve.io/inferenceservice=opt-125m-vllm -w
```

Clean up:
```bash
kubectl delete pod load-gen -n <your-namespace>
```

## Troubleshooting

### KEDA not scaling
1. Check ScaledObject status:
   ```bash
   kubectl describe scaledobject opt-125m-vllm-scaledobject -n <your-namespace>
   ```

2. Verify Prometheus connectivity (note the `/prometheus` path prefix on prokube):
   ```bash
   kubectl run curl-test --image=curlimages/curl --rm -it --restart=Never -- \
     curl -s 'http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090/prometheus/api/v1/query?query=up'
   ```

3. Check KEDA operator logs:
   ```bash
   kubectl logs -l app=keda-operator -n keda
   ```

### Metrics not appearing
1. Verify PodMonitor is picked up:
   ```bash
   kubectl get podmonitor -n <your-namespace>
   ```

2. Check if vLLM metrics are being scraped:
   ```bash
   kubectl run curl-test --image=curlimages/curl --rm -it --restart=Never -- \
     curl -s 'http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090/prometheus/api/v1/query?query={__name__=~"vllm:.*"}'
   ```

## References

- [KServe Issue #3561: Native KEDA integration](https://github.com/kserve/kserve/issues/3561)
- [KEDA Prometheus Scaler](https://keda.sh/docs/scalers/prometheus/)
- [vLLM Metrics](https://docs.vllm.ai/en/latest/serving/metrics.html)
