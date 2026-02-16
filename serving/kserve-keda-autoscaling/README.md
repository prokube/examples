# KServe Autoscaling with KEDA and Custom Metrics

This example demonstrates how to autoscale KServe InferenceServices using [KEDA](https://keda.sh/) with custom Prometheus metrics. This is particularly useful for LLM inference workloads where request-based autoscaling (Knative default) is not optimal.

## Why Custom Metrics for LLM Autoscaling?

Traditional request-based autoscaling doesn't work well for LLM inference because:

- **Token-level work**: LLM inference operates at token level, not request level. A single request can generate hundreds of tokens.
- **Variable latency**: Request latency varies significantly based on input/output token count.
- **Memory pressure**: LLM models require significant GPU memory (KV cache), which fills up based on concurrent requests.

Better metrics for LLM autoscaling include:
- **Token throughput**: Tokens generated per second
- **Time To First Token (TTFT)**: Latency until first token is generated
- **Time Per Output Token (TPOT)**: Average time per generated token
- **KV Cache utilization**: GPU memory used for attention cache
- **Number of running/waiting requests**: Queue depth

## Prerequisites

1. **KEDA** installed in the cluster:
   ```bash
   helm repo add kedacore https://kedacore.github.io/charts
   helm install keda kedacore/keda --namespace keda --create-namespace
   ```

2. **Prometheus** (kube-prometheus-stack recommended):
   ```bash
   helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
   helm install prometheus prometheus-community/kube-prometheus-stack --namespace monitoring --create-namespace
   ```

3. **KServe** with HuggingFace/vLLM runtime configured

4. **HuggingFace Token** (optional, for gated models):
   ```bash
   kubectl create secret generic hf-secret --from-literal=HF_TOKEN=<your-token> -n developer1
   ```

## Files

| File | Description |
|------|-------------|
| `inference-service.yaml` | KServe InferenceService for Qwen2.5-0.5B model |
| `scaled-object.yaml` | KEDA ScaledObject with multiple autoscaling strategies |
| `service-monitor.yaml` | ServiceMonitor, PodMonitor, and PrometheusRules for metrics collection |

## Deployment

### 1. Deploy the InferenceService

```bash
kubectl apply -f inference-service.yaml -n developer1
```

Wait for the model to be ready:
```bash
kubectl get inferenceservice qwen25-05b -n developer1 -w
```

### 2. Configure Prometheus Metrics Collection

Apply the ServiceMonitor to scrape vLLM metrics:
```bash
kubectl apply -f service-monitor.yaml -n developer1
```

Verify metrics are being scraped:
```bash
# Port-forward Prometheus
kubectl port-forward svc/prometheus-kube-prometheus-prometheus 9090:9090 -n monitoring

# Query for vLLM metrics
curl -s 'http://localhost:9090/api/v1/query?query=vllm_num_requests_running' | jq .
```

### 3. Deploy KEDA ScaledObject

First, identify the correct deployment name:
```bash
kubectl get deployments -n developer1 | grep qwen25-05b
```

Update `scaled-object.yaml` with the correct deployment name, then apply:
```bash
kubectl apply -f scaled-object.yaml -n developer1
```

Verify the ScaledObject:
```bash
kubectl get scaledobject -n developer1
kubectl describe scaledobject qwen25-05b-scaledobject -n developer1
```

## Autoscaling Strategies

This example includes three ScaledObject variants:

### 1. Token Throughput Based (Default)
Scales based on average token generation throughput and number of running requests:
```yaml
triggers:
  - type: prometheus
    metadata:
      query: avg(rate(vllm:generation_tokens_total[1m]))
      threshold: "100"
```

### 2. GPU Utilization Based
Scales based on GPU memory utilization (requires DCGM exporter):
```yaml
triggers:
  - type: prometheus
    metadata:
      query: avg(DCGM_FI_DEV_MEM_COPY_UTIL{pod=~"qwen25-05b-predictor.*"})
      threshold: "80"
```

### 3. Power Consumption Based
Scales based on power consumption metrics from [Kepler](https://github.com/sustainable-computing-io/kepler):
```yaml
triggers:
  - type: prometheus
    metadata:
      query: sum(rate(kepler_container_joules_total{container_name=~"qwen25-05b.*"}[5m]))
      threshold: "100"
```

## vLLM Metrics Reference

vLLM exposes metrics at `/metrics` endpoint:

| Metric | Description |
|--------|-------------|
| `vllm_num_requests_running` | Number of requests currently being processed |
| `vllm_num_requests_waiting` | Number of requests waiting in queue |
| `vllm_gpu_cache_usage_perc` | GPU KV cache utilization percentage |
| `vllm_generation_tokens_total` | Total number of generated tokens |
| `vllm_time_to_first_token_seconds` | Histogram of TTFT |
| `vllm_time_per_output_token_seconds` | Histogram of TPOT |

## Testing Autoscaling

Generate load to trigger autoscaling:

```bash
# Get the inference URL
ISVC_URL=$(kubectl get inferenceservice qwen25-05b -n developer1 -o jsonpath='{.status.url}')

# Send requests in a loop
for i in {1..100}; do
  curl -X POST "${ISVC_URL}/v1/completions" \
    -H "Content-Type: application/json" \
    -d '{
      "model": "qwen25-05b",
      "prompt": "Write a long story about",
      "max_tokens": 500
    }' &
done
```

Monitor scaling:
```bash
# Watch replica count
kubectl get deployment -n developer1 -w

# Check KEDA metrics
kubectl get hpa -n developer1
```

## Troubleshooting

### KEDA not scaling
1. Check ScaledObject status:
   ```bash
   kubectl describe scaledobject qwen25-05b-scaledobject -n developer1
   ```

2. Verify Prometheus connectivity:
   ```bash
   kubectl run curl-test --image=curlimages/curl --rm -it -- \
     curl -s 'http://prometheus-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090/api/v1/query?query=up'
   ```

3. Check KEDA operator logs:
   ```bash
   kubectl logs -l app=keda-operator -n keda
   ```

### Metrics not appearing
1. Verify ServiceMonitor is picked up:
   ```bash
   kubectl get servicemonitor -n developer1
   ```

2. Check Prometheus targets:
   - Open Prometheus UI -> Status -> Targets
   - Look for `serviceMonitor/developer1/qwen25-05b-metrics`

## References

- [KServe Issue #3561: Native KEDA integration](https://github.com/kserve/kserve/issues/3561)
- [KEDA Prometheus Scaler](https://keda.sh/docs/scalers/prometheus/)
- [vLLM Metrics](https://docs.vllm.ai/en/latest/serving/metrics.html)
- [Kepler: Kubernetes Energy Metering](https://github.com/sustainable-computing-io/kepler)
