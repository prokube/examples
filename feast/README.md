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
so the notebook can read and write feature definitions remotely. It also adds
`traffic.sidecar.istio.io/excludeInboundPorts: "6570"` — see "Known
limitations" for why this is required.

### 4. Apply the istio workaround

The operator-generated Service has port name `http` and no `appProtocol`,
so istio mis-classifies gRPC traffic as HTTP/1.1 and breaks it. This
misleads **both** envoy sidecars — see `feast-istio-workaround.yaml` for
a full explanation. The fix requires three pieces:

```bash
sed 's/<name>/my-store/g; s/<namespace>/<your-namespace>/g' \
  feast-istio-workaround.yaml | kubectl apply -f -
```

### 5. Run the notebook

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
| `feast-istio-workaround.yaml` | Kubernetes manifests — alt-Service + DestinationRule for istio gRPC fix |
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

- **Istio gRPC workaround required.** The operator creates the registry Service
  with `name: http` and no `appProtocol`. This misleads *both* envoy sidecars:
  the client-side envoy downgrades to HTTP/1.1, and the server-side envoy
  builds its inbound listener as HTTP/1.1 and rejects HTTP/2 with a protocol
  error. The workaround bypasses the server-side envoy entirely
  (`excludeInboundPorts: "6570"` in `feast-cr.yaml`), fixes the client-side
  envoy via an alt-Service with `appProtocol: grpc`, and disables mTLS
  (`tls: DISABLE` DestinationRule) since the server-side envoy is no longer
  in the path to terminate it. All three are needed and explained in
  `feast-istio-workaround.yaml`. Once the operator sets `appProtocol: grpc`
  on its own Service upstream, all three workarounds become unnecessary.
- **Notebook RBAC** for FeatureStore CRs must be granted by the platform. On
  prokube this is already in place.
