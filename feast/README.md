# Feast Feature Store Example

A complete example of using [Feast](https://docs.feast.dev/) on prokube for
feature management in ML workflows.

**Scenario:** An online retailer wants to predict whether a customer will
return their next order. The notebook walks through defining customer features,
training a return-risk model, and serving predictions in real time.

> **Note:** This example uses a SQLite SQL registry at `/tmp` which does not survive
> pod restarts. SQLite SQL gives proper transactional semantics over the plain file
> registry with identical maintenance burden — no server, just a file. For persistence
> across sessions, mount the registry PVC and set `path: sqlite:////data/registry/registry.db`.
> For multi-replica or high-availability setups, switch to PostgreSQL — see the
> "Production Setup" section in the notebook.
>
> **Known issue (Feast ≤ 0.53):** `feast apply` deadlocks with SQLite SQL because
> `_apply_object` calls `apply_project` while holding an open write transaction,
> opening a second connection that can't acquire the write lock. Fixed in Feast 0.54.0
> ([upstream PR #5588](https://github.com/feast-dev/feast/pull/5588)). On older versions,
> or if the deadlock recurs, the notebook applies a `StaticPool` workaround — see the
> `store.apply` cell for details.

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
| `redis-cr.yaml` | Kubernetes manifest — deploys a Redis instance (OpsTree operator) |
| `feast-cr.yaml` | Kubernetes manifest — deploys the FeatureStore CR |
| `feature_store.yaml` | Feast SDK config template — the notebook generates this automatically |
| `feast_example.ipynb` | End-to-end notebook: retail return prediction with Feast |

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
| **Registry** | Stores feature definitions (entities, feature views, sources). Written on `feast apply`, read at startup. | SQLite SQL on PVC (`registry_type: sql`) | Plain file (`registry_type: file`); PostgreSQL/MySQL for multi-replica |
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
store.apply() ─────▶  SQLite SQL /tmp/registry.db  │
  (notebook)        │    - feature definitions          │
                    │    - transactional writes         │
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
- **Registry** (SQLite SQL): feature definitions. In notebook workflows, uses `sqlite:////tmp/registry.db`
  (ephemeral). Mount the registry PVC for persistence at `sqlite:////data/registry/registry.db`.
  The Feast server pod uses the registry PVC at `/data/registry/registry.db`.
- **Offline store** (parquet/PVC): historical feature data for training.
