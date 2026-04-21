# Minimal predictor

This custom predictor is a simple KServe predictor that multiplies all `values` from a
request with a factor. The factor is configured through an environment variable, which
means you can change the predictor output without rebuilding the image.


## Run/Debug locally

Install dependencies and activate the virtual environment:

```bash
uv sync
source .venv/bin/activate
```

Export the required environment variables:

```bash
export MODEL_NAME=model
export FACTOR=2
```

Run the predictor:

```bash
python main.py
```

Running Python directly from this subfolder starts KServe in-process, so **no
external domain is needed** for local debugging. You can send a test request to the
locally running server:

```bash
curl -X POST http://localhost:8080/v1/models/model:predict \
  -H "Content-Type: application/json" \
  -d '{"values": ["3.3", "62.3", "324"]}'
```

For debugging there is already a ready-to-use `launch.json` in the `.vscode` directory.
