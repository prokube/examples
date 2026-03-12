# Minimal transformer
This custom transformer takes initializes a connection to a given postgres cluster and
stores all request as well as the response in a tables. 

For this specific example the database is required to have a `inference_requests` and a
`inference_response` table. You can create them as follows.

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

First export all required environment variables. 

```bash 
export POSTGRES_URI=<your-uri>
```

To be able to connect to the predictor deploy the predictor in KServe and portforward
the VirtualService. The virtual service has the same name as your InferenceService.
Then run the main python file. 

```bash
python3 main.py --predictor_host localhost --model_name model
```

For debugging there is already a ready to use `launch.json` in the .vscode directory
