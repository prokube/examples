# Minimal shadow deployment

When you'd like to try a new model with production data without risking anything, a
shadow deployment might be a good fit.

This example contains everything you need to deploy your own custom transformer/predictor
and the corresponding resources to mirror the traffic.


## Structure

To be able to analyze the results of the shadow deployment (i.e. compare the
results of your "original" model with the results of the "shadow" model), you
need to store the request and response of each inference request for both, the
original and the shadow model. For this purpose, this example uses a custom KServe
transformer (**minimal-transformer**), that stores the request and response in a
Postgres database. For your own shadow deployment, you can use this
transformer as a template and modify it or write your own.

The **minimal-predictor** used in this example is a small custom
predictor that multiplies the input values with some factor that is defined in
an environment variable. This is especially useful for testing purposes of the
shadow deployment mechanism, since you don't have to build a new image if you'd
like to change the predictor output.

We used CrunchyLabs postgres-operator to deploy a postgres cluster in the same namespace
as the inference services. If you have the operator deployed in
your cluster, you can use the **postgres-cluster.yaml** to deploy the same database.

> [!Warning]
> Make sure to create all required tables before you deploy the inference service. The
> transformer does **not** create them. See the minimal-transformer README for the
> required schema.


## YAML files

This example ships with several YAML manifests that together define the full shadow
deployment on Kubernetes:

- **doubler-inference-service.yaml** — the primary `InferenceService`. It uses the
  minimal-predictor with `FACTOR=2` (i.e. the "production" model) and the
  minimal-transformer to persist every request/response to Postgres.
- **tripler-inference-service.yaml** — the shadow `InferenceService`. Identical
  setup but with `FACTOR=3`. It receives a mirrored copy of every request so you can
  compare its outputs against the primary model without serving real users.
- **postgres-cluster.yaml** — a CrunchyData `PostgresCluster` resource. Deploy this
  if you need a fresh Postgres instance managed by the postgres-operator.
- **istio/mirrored-inference-virtual-service.yaml** — an Istio `VirtualService` that
  exposes the primary inference service externally and mirrors 100 % of incoming
  traffic to the shadow service in parallel.
- **istio/mirrored-traffic-redirect-virtual-service.yaml** — a second `VirtualService`
  that rewrites and forwards the mirrored traffic from the primary service URL to the
  shadow service URL, adjusting the `Host` header so KServe routes it correctly.
- **istio/kustomization.yaml** — applies both Istio VirtualServices in one step via
  `kubectl apply -k istio/`.

> [!Note]
> The `uri` fields inside the VirtualService files embed the namespace and InferenceService
> names as path segments (e.g. `/serving/<namespace>/<isvc-name>/`). Kustomize cannot patch
> these string values automatically, so you must update them manually before deploying.


## Deployment steps

A shadow deployment is inherently sequential: the primary model serves real traffic first,
and the shadow is introduced later. Do **not** deploy both InferenceServices at the same
time in production — deploy the primary, verify it, then add the shadow.

No namespace is hardcoded in the manifests. Pass `-n <your-namespace>` to each `kubectl`
command, or set your current context namespace with (not needed if commands run from notebook):

```bash
kubectl config set-context --current --namespace=<your-namespace>
```

### 1. Postgres (optional — skip if you already have a database)

If you have the CrunchyData postgres-operator installed, deploy the cluster:

```bash
kubectl apply -f postgres-cluster.yaml
```

Wait for the cluster to be ready, then create the required tables (see the
[minimal-transformer README](minimal-transformer/README.md) for the schema). You can
run a one-off pod to do this:

```bash
kubectl run pg-init --rm -i --restart=Never --image=postgres:17 \
  --env="PGPASSWORD=<password>" \
  -- psql -h inferencing-postgres-primary.<your-namespace>.svc \
     -U transformer-admin -d scale-inference \
     -f /dev/stdin <<'EOF'
CREATE TABLE IF NOT EXISTS public.inference_requests (
  request_id uuid NOT NULL,
  request_time timestamp with time zone NULL,
  request_data json NULL,
  predict_url text NULL,
  created_at timestamp NULL,
  PRIMARY KEY (request_id)
);
CREATE TABLE IF NOT EXISTS public.inference_response(
  request_id uuid NOT NULL,
  request_data json NULL,
  created_at timestamp NULL,
  PRIMARY KEY (request_id)
);
EOF
```

### 2. Build and push images (optional — skip if using pre-built images)

Pre-built images are available at:
- `europe-west3-docker.pkg.dev/prokube-internal/prokube-customer/minimal-predictor:latest`
- `europe-west3-docker.pkg.dev/prokube-internal/prokube-customer/minimal-transformer:latest`

These are accessible from any prokube cluster via the `regcred-prokube` secret on the
`default-editor` service account. If you need to build your own:

```bash
docker build -t <your-registry>/minimal-predictor:latest minimal-predictor/
docker build -t <your-registry>/minimal-transformer:latest minimal-transformer/
docker push <your-registry>/minimal-predictor:latest
docker push <your-registry>/minimal-transformer:latest
```

Then update the `image` fields in both InferenceService YAMLs accordingly.

### 3. Deploy the primary InferenceService

```bash
kubectl apply -f doubler-inference-service.yaml
kubectl wait --for=condition=Ready inferenceservice/double-minimal-custom-inference --timeout=120s
```

### 4. Deploy the shadow InferenceService

Once the primary is verified and serving traffic:

```bash
kubectl apply -f tripler-inference-service.yaml
kubectl wait --for=condition=Ready inferenceservice/triple-minimal-custom-inference --timeout=120s
```

### 5. Enable traffic mirroring

Update the `uri` paths and the `hosts`/`Host` fields in both VirtualService files
under `istio/` to match your domain and namespace, then apply:

```bash
kubectl apply -k istio/
```

### 6. Verify mirroring and compare results

Send a few requests to the mirrored endpoint (the response always comes from the
primary — the shadow receives a silent fire-and-forget copy):

```bash
curl -s -X POST \
  "http://<primary-isvc>.<namespace>.svc.cluster.local/v1/models/model:predict" \
  -H "Content-Type: application/json" \
  -d '{"values": ["3.3", "62.3", "324"]}'
```

Both the primary and the shadow transformer write every request and response to the
same Postgres database. To compare their outputs, query the tables — the `predict_url`
column in `inference_requests` identifies which ISVC handled each request:

```bash
# Open a psql session
kubectl run pg-query --rm -i --restart=Never --image=postgres:17 \
  --env="PGPASSWORD=<password>" \
  -- psql -h inferencing-postgres-primary.<namespace>.svc \
     -U transformer-admin -d scale-inference
```

```sql
-- Requests per model
SELECT predict_url, COUNT(*) FROM inference_requests GROUP BY predict_url;

-- Compare primary vs shadow responses side-by-side for the same request
SELECT
  req.predict_url,
  req.request_data  AS input,
  res.request_data  AS output,
  req.created_at
FROM inference_requests req
JOIN inference_response res USING (request_id)
ORDER BY req.created_at DESC
LIMIT 20;
```

If the shadow rows are missing, check its transformer logs:

```bash
kubectl logs -l serving.kserve.io/inferenceservice=triple-minimal-custom-inference \
  -c kserve-container -n <namespace>
```


## Development and debugging

The predictor and transformer are two independent `uv`-managed projects. Both are
structured in a similar way and can be treated similarly.

> [!Note]
> The debugging configuration differs slightly between the two projects. Please consult
> each component's own README for details.

Install all dependencies and activate the virtual environment from inside each
component directory:

```bash
uv sync
source .venv/bin/activate
```

### Local testing

When running the components locally (i.e. starting Python directly from the project
subfolder), KServe is started in-process — **no external domain is required**.

Send a request directly to the locally running server (default port 8080):

```bash
curl -X POST http://localhost:8080/v1/models/model:predict \
  -H "Content-Type: application/json" \
  -d '{"values": ["3.3", "62.3", "324"]}'
```

To test against a service already deployed in the cluster, send a request directly
to the service DNS name from any pod in the same namespace — no gateway or API key
needed for cluster-internal calls:

```bash
curl -s -X POST \
  "http://double-minimal-custom-inference.<your-namespace>.svc.cluster.local/v1/models/model:predict" \
  -H "Content-Type: application/json" \
  -d '{"values": ["3.3", "62.3", "324"]}'
```

To reach the service externally, set `DOMAIN_NAME`, `PROFILE_NAME`, and `X_API_KEY`:

```bash
curl -L -X POST \
  "$DOMAIN_NAME/serving/$PROFILE_NAME/mirrored-inference/v1/models/model:predict" \
  -H "Content-Type: application/json" \
  -H "x-api-key: ${X_API_KEY}" \
  -d '{"values": ["3.3", "62.3", "324"]}'
```
