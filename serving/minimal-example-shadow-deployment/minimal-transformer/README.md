# Minimal transformer

This custom transformer initializes a connection to a given Postgres cluster and
stores all requests as well as the responses in dedicated tables.

For this specific example the database is required to have an `inference_requests` and an
`inference_response` table. Create them as follows before deploying the transformer:

```sql
CREATE TABLE public.inference_requests (
	request_id uuid NOT NULL,
	request_time timestamp with time zone NULL,
	request_data json NULL,
	predict_url text NULL,
	created_at timestamp NULL,
	PRIMARY KEY (request_id)
);

CREATE TABLE public.inference_response(
	request_id uuid NOT NULL,
	request_data json NULL,
	created_at timestamp NULL,
	PRIMARY KEY (request_id)
);
```


## Run/Debug locally

Install dependencies and activate the virtual environment:

```bash
uv sync
source .venv/bin/activate
```

Export the required environment variables:

```bash
export POSTGRES_URI=<your-uri>
```

Running Python directly from this subfolder starts KServe in-process, so **no
external domain or port-forward to the cluster gateway is needed** for the transformer
itself. You do, however, need a reachable predictor. The simplest approach is to
deploy the predictor in KServe and port-forward its service:

```bash
kubectl port-forward svc/<predictor-service-name> 8080:80 -n <namespace>
```

Then start the transformer:

```bash
python main.py --predictor_host localhost --model_name model
```

For debugging there is already a ready-to-use `launch.json` in the `.vscode` directory.
