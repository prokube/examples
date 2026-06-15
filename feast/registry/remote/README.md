# Remote registry mode

The notebook talks to the registry via the **gRPC server** that the Feast
Operator exposes from the FeatureStore CR. Feature definitions you `apply()`
persist on the operator-managed PVC and are visible to every other client in
the namespace.

## How it works

- `feast apply` sends definitions to the registry gRPC server over the
  operator's native registry Service.
- All clients in the namespace share the same registry — no need to re-run
  `apply()` after a notebook restart.
- The operator publishes a `feast-<name>-client` ConfigMap with the
  connection details; the notebook reads it automatically.

## Trade-offs vs local mode

| | Remote (this folder) | Local |
|---|---|---|
| Registry persistence | Persistent on operator PVC | Ephemeral (`/tmp`) by default |
| Shared across clients | Yes | No |
| Setup complexity | Higher | Low |

## Setup

Follow the top-level README through the Redis and `feast-redis-config` steps,
then:

```bash
# 1. Deploy the FeatureStore CR
kubectl apply -f registry/remote/feast-cr.yaml
kubectl get featurestore -n <your-namespace> -w   # wait until Ready
```

Then open the notebook and select **Remote** when prompted.

## Files

| File | Purpose |
|------|---------|
| `feast-cr.yaml` | FeatureStore CR with `server: {}` to enable the gRPC registry |
| `feature_store.yaml` | Feast SDK config template (notebook writes this from the operator ConfigMap) |
| `network-policies.yaml` | CNI-layer NetworkPolicies for registry and Redis isolation |
