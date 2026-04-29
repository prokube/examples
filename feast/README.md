# Feast Feature Store Examples

These examples demonstrate how to use [Feast](https://docs.feast.dev/) on prokube
for feature management in ML workflows.

## Prerequisites

- Feast must be enabled on your cluster (ask your admin)
- You have `kubectl` access to your Kubeflow profile namespace

## Quick Start

### 1. Deploy a Redis instance

Create a password secret and a Redis CR in your namespace:

```bash
# Generate a random password
kubectl create secret generic redis-feast \
  -n <your-namespace> \
  --from-literal=password=$(openssl rand -base64 24 | tr -d '/')

# Deploy the Redis CR
kubectl apply -f redis-cr.yaml   # see file below — edit namespace first
kubectl get redis -n <your-namespace> -w
```

`redis-cr.yaml` is a plain Kubernetes manifest for the OpsTree Redis operator.
Create it with the contents shown in the prokube [user docs](https://docs.prokube.ai/user_docs/feast/).

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

### 3. Deploy a FeatureStore

Edit `feast-cr.yaml` to set your namespace, then:

```bash
kubectl apply -f feast-cr.yaml
kubectl get featurestore -n <your-namespace> -w   # wait until Ready
```

### 4. Run the notebook

Open `feast_example.ipynb` in your Kubeflow notebook. The notebook reads the
`feast-redis-config` secret automatically and builds `feature_store.yaml` for you.

## Files

| File | What it is |
|------|------------|
| `feast-cr.yaml` | Kubernetes manifest — deploys the FeatureStore CR |
| `feature_store.yaml` | Feast SDK config — tells the Python client where registry and stores are |
| `features.py` | Feature definitions — entities, data sources, feature views |
| `feast_example.ipynb` | End-to-end notebook: generate data, apply, train, materialize, serve |

### Why two YAML files?

`feast-cr.yaml` is a **Kubernetes resource** (`kind: FeatureStore`) that the operator
reads to provision PVCs and the Feast server pod. You apply it once with `kubectl`.

`feature_store.yaml` is a **Feast SDK config file** (fixed filename — Feast convention)
that the Python client and CLI read to know how to connect to the registry and stores.
You use it in notebooks and scripts.

## Architecture

Feast has three stores. Here is what each one does and which backend prokube uses:

| Store | Purpose | Prokube default | Alternatives |
|-------|---------|-----------------|--------------|
| **Registry** | Stores feature definitions (entities, feature views, sources). Written on `feast apply`, read at startup. | SQLite on PVC | SQL databases (PostgreSQL, etc.) for multi-replica or shared setups |
| **Online store** | Holds the *latest* feature value per entity. Read on every inference request — latency critical. | Redis (your `Redis` CR) | SQLite on PVC (dev/test only; not multi-replica safe) |
| **Offline store** | Historical feature records for point-in-time joins during training. Batch workload, not on serving path. | Parquet/file on PVC | Dask (same parquet files, distributed compute — use only if data exceeds pod memory); cloud warehouses (BigQuery, Snowflake, Redshift) |

The offline store default is `type: file` (pandas). You can switch to `type: dask` in
`feast-cr.yaml` if your datasets are too large to fit in memory, but it adds complexity
and is rarely needed.

```
                    ┌─────────────────────────────────┐
                    │        Your Namespace            │
                    │                                  │
                    │  Redis CR (redis-feast)           │
                    │    - your private Redis instance  │
                    │                                  │
  feast apply ──────▶  SQLite /tmp/registry.db        │
  (notebook)        │    - feature definitions          │
                    │    - entity schemas               │
                    │                                  │
  materialize ──────▶  Redis online store              │
                    │    - latest feature values        │
                    │    - sub-ms latency               │
                    │    - persistent across sessions   │
                    │                                  │
  historical  ──────▶  Parquet on PVC (offline store)  │
  features          │    - time-series feature data     │
                    │                                  │
                    │  Feast Server pod                │
                    │    - HTTP API for online features │
                    │    - registry on PVC (/data/...)  │
                    └─────────────────────────────────┘
```

- **Redis** (per-namespace): your private online store. You own and manage it.
- **Registry** (SQLite): feature definitions. In notebook workflows, uses `/tmp/registry.db`.
  The Feast server pod uses the registry PVC at `/data/registry/registry.db`.
- **Offline store** (parquet/PVC): historical feature data for training.
