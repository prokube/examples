# Remote registry mode

The notebook talks to the registry via the **gRPC server** that the Feast
Operator exposes from the FeatureStore CR. Feature definitions you `apply()`
persist on the operator-managed PVC and are visible to every other client in
the namespace.

## How it works

- `feast apply` sends definitions to the registry gRPC server over the
  alt-Service created by `feast-istio-workaround.yaml`.
- All clients in the namespace share the same registry — no need to re-run
  `apply()` after a notebook restart.
- The operator publishes a `feast-<name>-client` ConfigMap with the
  connection details; the notebook reads it automatically.

## Trade-offs vs local mode

| | Remote (this folder) | Local |
|---|---|---|
| Registry persistence | Persistent on operator PVC | Ephemeral (`/tmp`) by default |
| Shared across clients | Yes | No |
| ODFVs | Require a monkey-patch (Feast ≤ 0.63 bug with dill+typeguard) | Work out of the box |
| Istio workaround | Required (3-part) | Not needed |
| Setup complexity | Higher | Low |

## When to remove this workaround

This mode requires `feast-istio-workaround.yaml` because the Feast Operator
creates the registry Service with `name: http` and no `appProtocol`, causing
Istio to misclassify gRPC traffic as HTTP/1.1.

Once [feast-dev/feast#6367](https://github.com/feast-dev/feast/pull/6367) is
merged and you upgrade the operator, the workaround becomes unnecessary:
- Remove `feast-istio-workaround.yaml` and its `kubectl apply` step
- Remove the `podAnnotations` block from `feast-cr.yaml`
- Remove the `PandasTransformation.from_proto` monkey-patch from the notebook

At that point, remote mode becomes the clear default and local mode can be
retired.

## Setup

Follow the top-level README through the Redis and `feast-redis-config` steps,
then:

```bash
# 1. Deploy the FeatureStore CR
kubectl apply -f registry/remote/feast-cr.yaml
kubectl get featurestore -n <your-namespace> -w   # wait until Ready

# 2. Apply the Istio workaround
sed 's/<name>/my-store/g; s/<namespace>/<your-namespace>/g' \
  registry/remote/feast-istio-workaround.yaml | kubectl apply -f -
```

Then open the notebook and select **Remote** when prompted.

## Files

| File | Purpose |
|------|---------|
| `feast-cr.yaml` | FeatureStore CR with `server: {}` and Istio pod annotation |
| `feature_store.yaml` | Feast SDK config template (notebook writes this from the operator ConfigMap) |
| `feast-istio-workaround.yaml` | Alt-Service + DestinationRule to fix Istio gRPC misclassification |
