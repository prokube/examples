# Feast Feature Store Example

A complete example of using [Feast](https://docs.feast.dev/) on prokube for
feature management in ML workflows.

**Scenario:** An online retailer wants to predict whether a customer will
return their next order. The notebook walks through defining customer features,
training a return-risk model, and serving predictions in real time.

The notebook talks to the **registry gRPC server** that the Feast Operator
exposes from the FeatureStore CR. Feature definitions you `apply()` from the
notebook persist on the operator-managed PVC and are visible to every other
client in the namespace.

## Prerequisites

- Feast must be enabled on your cluster (ask your admin)
- You have `kubectl` access to your Kubeflow profile namespace
- A cluster admin has applied `feast-notebook-rbac.yaml` once per cluster
  (grants notebook ServiceAccounts read access to FeatureStore CRs)

## Quick Start

### 1. Deploy a Redis instance

Create a password secret and a Redis CR in your namespace:

```bash
# Generate a random password
kubectl create secret generic redis-feast \
  -n <your-namespace> \
  --from-literal=password=$(openssl rand -base64 24 | tr -d '/')

# Deploy the Redis CR (edit namespace in redis-cr.yaml first)
kubectl apply -f redis-cr.yaml
kubectl get redis -n <your-namespace> -w
```

### 2. Create the Feast Redis secret

```bash
NAMESPACE=<your-namespace>
PASSWORD=$(kubectl get secret redis-feast -n $NAMESPACE \
  -o jsonpath='{.data.password}' | base64 -d)

cat > /tmp/redis-config.yaml << EOF
connection_string: "redis-feast.${NAMESPACE}.svc.cluster.local:6379,password=${PASSWORD}"
EOF

kubectl create secret generic feast-redis-config \
  -n $NAMESPACE \
  --from-file=redis=/tmp/redis-config.yaml

rm /tmp/redis-config.yaml
```

### 3. Deploy the FeatureStore

Edit `feast-cr.yaml` to set your namespace, then:

```bash
kubectl apply -f feast-cr.yaml
kubectl get featurestore -n <your-namespace> -w   # wait until Ready
```

This CR enables the **registry gRPC server** (`services.registry.local.server`)
so the notebook can read and write feature definitions remotely. It also sets
`sidecar.istio.io/inject: "false"` on the feast-server pod — the registry only
carries feature *metadata*, and istio's protocol detection mis-classifies the
operator's registry Service as HTTP/1.1, breaking gRPC. See "Known limitations"
below for details.

### 4. Run the notebook

Open `feast_example.ipynb` in your Kubeflow notebook. The first cell
auto-discovers the FeatureStore CR in the current namespace, reads the
operator-published `feast-<name>-client` ConfigMap and the Redis secret it
references, then writes a `feature_store.yaml` that points at the remote
registry and the local Redis online store.

## Files

| File | What it is |
|------|------------|
| `redis-cr.yaml` | Kubernetes manifest — deploys a Redis instance (OpsTree operator) |
| `feast-cr.yaml` | Kubernetes manifest — deploys the FeatureStore CR with registry server enabled |
| `feast-notebook-rbac.yaml` | ClusterRole granting notebook SAs read access to FeatureStore CRs (apply once per cluster; not needed on prokube — already in `kubeflow-roles`) |
| `feature_store.yaml` | Feast SDK config template — the notebook generates this automatically |
| `feast_example.ipynb` | End-to-end notebook: retail return prediction with Feast |

### Why two Feast YAML files?

`feast-cr.yaml` is a **Kubernetes resource** (`kind: FeatureStore`) that the
operator reads to provision PVCs, the Feast server pod, and the registry gRPC
service. You apply it once with `kubectl`.

`feature_store.yaml` is a **Feast SDK config file** (fixed filename — Feast
convention) that the Python client and CLI read to know how to connect to the
registry and stores. The notebook builds it for you from the operator's
client ConfigMap; you don't edit it directly.

## Architecture

Feast has three stores. Here is what each one does and which backend prokube uses:

| Store | Purpose | Prokube default | Alternatives |
|-------|---------|-----------------|--------------|
| **Registry** | Feature definitions (entities, feature views, sources). Written on `apply()`, read at startup. | gRPC server backed by SQLite on PVC | PostgreSQL for multi-replica feast-server |
| **Online store** | Latest feature value per entity. Read on every inference — latency critical. | Redis (your `Redis` CR) | SQLite on PVC (dev/test only) |
| **Offline store** | Historical feature records for point-in-time joins during training. | Parquet/file on PVC | Dask (distributed); cloud warehouses |

```
                    ┌──────────────────────────────────────┐
                    │           Your Namespace             │
                    │                                      │
                    │  Redis CR (redis-feast)               │
                    │    - your private Redis instance      │
                    │                                      │
  store.apply() ──gRPC──▶  Registry Server (Feast Operator)│
  (notebook)        │    - feature definitions on PVC       │
                    │                                      │
  materialize ──────▶  Redis online store                  │
                    │    - latest feature values            │
                    │    - sub-ms latency                   │
                    │                                      │
  historical  ──────▶  Parquet on PVC (offline store)      │
  features          │    - time-series feature data         │
                    │                                      │
                    │  Feast Server pod                    │
                    │    - registry gRPC :6570              │
                    │    - online HTTP                      │
                    │    - PVCs for registry & offline data │
                    └──────────────────────────────────────┘
```

## Known limitations

- **No on-demand feature views.** Feast 0.63 has a bug where ODFVs round-tripped
  through a remote registry hang on invocation (the deserialized UDF object
  gets stuck somewhere in the typeguard-instrumented code path). Until that's
  fixed upstream, the notebook computes derived columns in plain pandas after
  `get_historical_features` / `get_online_features`. Switch to a local registry
  if you need ODFVs.
- **Istio sidecar disabled on the feast-server pod.** The operator generates
  the registry Service with port name `http` and no `appProtocol`, so istio
  mis-classifies gRPC traffic and breaks it. The simplest fix — used in
  `feast-cr.yaml` — is `sidecar.istio.io/inject: "false"` on the feast-server
  pod. The registry only carries feature *metadata* (entity schemas, feature
  view names, data source paths), so the impact is small. Feature *values* in
  Redis and on the offline-store PVC are unaffected. Rely on NetworkPolicy at
  the namespace level for cross-namespace isolation.
- **Notebook RBAC** for FeatureStore CRs comes from `kubeflow-roles` on
  prokube. On other Kubeflow installs, apply `feast-notebook-rbac.yaml`.
