# Feast Feature Store Example

A complete example of using [Feast](https://docs.feast.dev/) on prokube for
feature management in ML workflows.

**Scenario:** An online retailer wants to predict whether a customer will
return their next order. The notebook walks through defining customer features,
training a return-risk model, and serving predictions in real time.

## Prerequisites

- Feast must be enabled on your cluster (ask your admin)
- You have `kubectl` access to your Kubeflow profile namespace

## Quick Start

### 1. Deploy a Redis instance

```bash
kubectl create secret generic redis-feast \
  -n <your-namespace> \
  --from-literal=password=$(openssl rand -base64 24 | tr -d '/')

kubectl apply -f redis-cr.yaml   # edit namespace first
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

### 3. Choose a registry mode and deploy the FeatureStore

There are two registry modes. **Pick one:**

| | Local | Remote |
|---|---|---|
| **Registry** | SQLite SQL on `/tmp` (ephemeral) or PVC (persistent) | gRPC server on operator PVC (persistent, shared) |
| **Good for** | Single user, quick iteration | Teams sharing definitions across clients |

**Local:**
```bash
kubectl apply -f registry/local/feast-cr.yaml   # edit namespace first
kubectl get featurestore -n <your-namespace> -w
```

**Remote:**
```bash
kubectl apply -f registry/remote/feast-cr.yaml   # edit namespace first
kubectl get featurestore -n <your-namespace> -w
```

### 4. Run the notebook

Open `feast_example.ipynb`. The first cell will ask which registry mode you
chose — select it there and run all cells.

## Files

```
feast/
  feast_example.ipynb              End-to-end notebook (works with both modes)
  redis-cr.yaml                    Deploys a Redis instance (OpsTree operator)
  registry/
    local/
      feast-cr.yaml                FeatureStore CR — local SQLite SQL registry
      feature_store.yaml           Feast SDK config template
      README.md                    Local mode details and trade-offs
    remote/
      feast-cr.yaml                FeatureStore CR — remote gRPC registry server
      feature_store.yaml           Feast SDK config template
      network-policies.yaml        CNI-layer NetworkPolicies for isolation
      README.md                    Remote mode details and trade-offs
```

## Architecture

Feast has three stores:

| Store | Purpose | Backend |
|-------|---------|---------|
| **Registry** | Feature definitions (entities, feature views, sources). Written on `feast apply`. | Local: SQLite SQL file. Remote: gRPC server on operator PVC. |
| **Online store** | Latest feature value per entity. Read on every inference — latency critical. | Redis (your `Redis` CR) |
| **Offline store** | Historical feature records for point-in-time joins during training. | Parquet on PVC |

```
                    ┌──────────────────────────────────────┐
                    │           Your Namespace             │
                    │                                      │
                    │  Redis CR (redis-feast)               │
                    │                                      │
  store.apply() ───▶  Registry                             │
  (notebook)        │    local:  sqlite:////tmp/registry.db │
                    │    remote: gRPC → operator PVC        │
                    │                                      │
  materialize ──────▶  Redis online store                  │
                    │                                      │
  historical  ──────▶  Parquet on PVC (offline store)      │
  features          │                                      │
                    └──────────────────────────────────────┘
```
