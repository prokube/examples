# Feast Feature Store Example

An end-to-end example of using [Feast](https://docs.feast.dev/) on prokube to
manage features for training and real-time inference.

**Scenario:** An online retailer wants to predict whether a customer will
return their next order. The notebook defines customer features, trains a
return-risk model, and serves predictions from online features.

Feast runs as a Python library in your Lab. prokube does not need a Feast
server or operator, and no administrator action is required.

## Quick start

1. Open a JupyterLab Lab in your workspace. The `examples` repository is
   usually cloned into your home directory already.
2. Open `feast/feast_example.ipynb` and run all cells.

The setup cell installs Feast, starts Redis in your workspace, and checks that
the notebook can reach it.

## What the example creates

| Resource | Where | Purpose |
|---|---|---|
| Secret `feast-redis` | Workspace namespace | Random Redis password |
| StatefulSet and Service `feast-redis`, PVC `data-feast-redis-0` | Workspace namespace | Redis, the online store (`redis.yaml`) |
| `feast-example/registry.db` | Bucket `<workspace>-data` | Feast registry: the feature definitions |
| `feast-example/data/customer_orders.parquet` | Bucket `<workspace>-data` | Offline store: historical feature data |

Redis holds only data that `materialize()` can rebuild from the Parquet files,
so it runs as a single pod without replication or backups. For production,
ask your administrator for a managed Redis or PostgreSQL instance.

## Files

```
feast/
  feast_example.ipynb        End-to-end notebook
  feature_store.yaml         Feast configuration; reads its locations from environment variables
  redis.yaml                 Redis StatefulSet and Service for the online store
  redis-networkpolicy.yaml   Allows workspace pods to reach Redis when an egress profile is assigned
```

## Workspaces with an egress profile

An egress profile restricts outbound traffic of every pod in the workspace,
including traffic to other pods in the same workspace. If the setup cell
reports that Redis is not reachable, apply the included NetworkPolicy and
re-run the cell:

```bash
kubectl apply -f redis-networkpolicy.yaml
```

## Use the features from another workload

A pipeline step, inference service, or other pod in the same workspace can
read the features with the same `feature_store.yaml`. Give its container
these environment variables:

```yaml
env:
  - name: FEAST_REGISTRY_PATH
    value: s3://<workspace>-data/feast-example/registry.db
  - name: REDIS_PASSWORD
    valueFrom:
      secretKeyRef:
        name: feast-redis
        key: password
  - name: FEAST_REDIS_CONNECTION_STRING
    value: feast-redis:6379,password=$(REDIS_PASSWORD)
  - name: AWS_ENDPOINT_URL
    value: <same value as in your Lab: echo $AWS_ENDPOINT_URL>
  - name: AWS_ACCESS_KEY_ID
    valueFrom:
      secretKeyRef:
        name: s3creds
        key: AWS_ACCESS_KEY_ID
  - name: AWS_SECRET_ACCESS_KEY
    valueFrom:
      secretKeyRef:
        name: s3creds
        key: AWS_SECRET_ACCESS_KEY
```

Then read online features by feature service name:

```python
from feast import FeatureStore

store = FeatureStore(repo_path="/path/to/feast")  # directory with feature_store.yaml
features = store.get_online_features(
    features=store.get_feature_service("customer_risk_service"),
    entity_rows=[{"customer_id": 42}],
).to_dict()
```

## Clean up

Run from the `feast/` directory in a Lab terminal:

```bash
kubectl delete -f redis.yaml --ignore-not-found
kubectl delete pvc data-feast-redis-0 --ignore-not-found
kubectl delete secret feast-redis --ignore-not-found
rclone delete minio:<workspace>-data/feast-example
```
