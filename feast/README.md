# Feast Feature Store Example

A complete example of using [Feast](https://docs.feast.dev/) on prokube for
feature management in ML workflows.

**Scenario:** An online retailer wants to predict whether a customer will
return their next order. The notebook walks through defining customer features,
training a return-risk model, and serving predictions in real time.

## Quick Start

1. Feast must be enabled on your cluster (ask your admin)
2. Clone this repository to your notebook server
3. Open `feast_example.ipynb` from the `feast/` directory and run all cells

The notebook's **Infrastructure setup** cell handles everything automatically:
Redis, secrets, FeatureStore CR, and (for remote mode) NetworkPolicies.

## Registry modes

There are two registry modes. Select one in the notebook when prompted:

| | Local | Remote |
|---|---|---|
| **Registry** | SQLite SQL on `/tmp` (ephemeral) | gRPC server on operator PVC (persistent, shared) |
| **Good for** | Single user, quick iteration | Teams sharing definitions across clients |

## Files

```
feast/
  feast_example.ipynb              End-to-end notebook (works with both modes)
  redis-cr.yaml                    Redis instance CR (OpsTree operator)
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
                    │  Redis CR (redis-feast)              │
                    │                                      │
  store.apply() ───▶  Registry                             │
  (notebook)        │   local:  sqlite:////tmp/registry.db │
                    │   remote: gRPC → operator PVC        │
                    │                                      │
  materialize ──────▶  Redis online store                  │
                    │                                      │
  historical  ──────▶  Parquet on PVC (offline store)      │
  features          │                                      │
                    └──────────────────────────────────────┘
```
