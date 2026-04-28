# Feast Feature Store Examples

These examples demonstrate how to use [Feast](https://docs.feast.dev/) on prokube
for feature management in ML workflows.

## Prerequisites

- Feast must be enabled on your cluster (ask your admin)
- A `FeatureStore` CR must be created in your workspace (see below)
- The `feast-registry-config` secret must exist in your namespace

## Quick Start

### 1. Create a FeatureStore in your workspace

Apply the example CR (edit the namespace):

```bash
kubectl apply -f featurestore.yaml
```

Wait for it to become ready:

```bash
kubectl get featurestore -n <your-namespace> -w
```

### 2. Get your client configuration

The operator creates a ConfigMap with connection info:

```bash
kubectl get configmap feast-<name>-client -n <your-namespace> \
  -o jsonpath='{.data.feature_store\.yaml}'
```

Save this as `feature_store.yaml` in your working directory. This config only
contains the **online store** endpoint (remote HTTP). For operations that need
registry access (`feast apply`, `get_historical_features`, `materialize`), you
need to build a full config — see the notebook example.

### 3. Run the notebook

Open `feast_example.ipynb` in your Kubeflow notebook and follow the steps.

## Examples

| File | Description |
|------|-------------|
| `featurestore.yaml` | FeatureStore CR to deploy in your namespace |
| `feature_store.yaml` | Client config template (fill in your namespace + registry) |
| `features.py` | Feature definitions — entities, sources, feature views |
| `feast_example.ipynb` | End-to-end notebook: define, apply, materialize, train, serve |

## Architecture

```
                    ┌─────────────────────────────────┐
                    │        Your Namespace            │
                    │                                  │
  feast apply ──────▶  MariaDB (registry)              │
                    │    - feature definitions          │
                    │    - entity schemas               │
                    │                                  │
  materialize ──────▶  SQLite on PVC (online store)    │
                    │    - latest feature values        │
                    │                                  │
  historical  ──────▶  Parquet on PVC (offline store)  │
  features          │    - time-series feature data     │
                    │                                  │
                    │  Feast Server (deployment)        │
                    │    - serves online features       │
                    └─────────────────────────────────┘
```

- **Registry** (MariaDB): stores metadata — what features exist, their schemas,
  data sources. Shared across all Feast processes in your namespace.
- **Online store** (SQLite/PVC): key-value store with the *latest* feature values
  per entity. Updated by `feast materialize`. Used for real-time inference.
- **Offline store** (Dask/file/PVC): historical feature data in parquet files.
  Used for training dataset generation with point-in-time correctness.
