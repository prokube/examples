# Feast Feature Store Examples

These examples demonstrate how to use [Feast](https://docs.feast.dev/) on prokube
for feature management in ML workflows.

## Prerequisites

- Feast must be enabled on your cluster (ask your admin)
- A `feast-redis-config` secret must exist in your namespace (see step 1)
- A `FeatureStore` CR must be created in your workspace (see step 2)

## Quick Start

### 1. Create the Redis secret

Ask your admin for the Redis host and password, then:

```bash
kubectl create secret generic feast-redis-config \
  -n <your-namespace> \
  --from-literal=redis='connection_string: "<redis-host>:6379,password=<password>"'
```

> **Note:** The secret key must be named `redis` and the value must be a YAML map.
> Use `host:port,password=...` format — **not** a `redis://` URI.

### 2. Create a FeatureStore in your workspace

Edit `featurestore.yaml` to set your namespace, then apply:

```bash
kubectl apply -f featurestore.yaml
```

Wait for it to become ready:

```bash
kubectl get featurestore -n <your-namespace> -w
```

### 3. Configure your feature_store.yaml

Edit `feature_store.yaml` with your Redis connection details. Use this file in
your notebooks or scripts to run `feast apply`, `materialize`, and retrieve features.

### 4. Run the notebook

Open `feast_example.ipynb` in your Kubeflow notebook and follow the steps.

## Examples

| File | Description |
|------|-------------|
| `featurestore.yaml` | FeatureStore CR to deploy in your namespace |
| `feature_store.yaml` | Client config template (fill in Redis details) |
| `features.py` | Feature definitions — entities, sources, feature views |
| `feast_example.ipynb` | End-to-end notebook: define, apply, materialize, train, serve |

## Architecture

```
                    ┌─────────────────────────────────┐
                    │        Your Namespace            │
                    │                                  │
  feast apply ──────▶  SQLite on PVC (registry)       │
                    │    - feature definitions          │
                    │    - entity schemas               │
                    │                                  │
  materialize ──────▶  Redis (online store)            │
                    │    - latest feature values        │
                    │    - sub-ms latency               │
                    │                                  │
  historical  ──────▶  Parquet on PVC (offline store)  │
  features          │    - time-series feature data     │
                    │                                  │
                    │  Feast Server (deployment)        │
                    │    - serves online features       │
                    └─────────────────────────────────┘
```

- **Registry** (SQLite/PVC): stores metadata — what features exist, their schemas,
  data sources. Accessible from within your namespace.
- **Online store** (Redis): key-value store with the *latest* feature values
  per entity. Updated by `feast materialize`. Used for real-time inference.
- **Offline store** (Dask/file/PVC): historical feature data in parquet files.
  Used for training dataset generation with point-in-time correctness.
