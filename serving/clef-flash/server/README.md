# CLEF-Flash SystemOne server

This package serves the decision head released with
[`Cloudflare/clef-flash`](https://huggingface.co/Cloudflare/clef-flash). It
loads `joint_schema_model.py` from a local model snapshot and exposes the
Jev/SystemOne-compatible `POST /v1/systemone` endpoint. It does not use the
Qwen text-generation interface.

The model card currently specifies Python 3.12, PyTorch 2.11, and Transformers
5.10.2. The full BF16 snapshot occupies about 19 GB and requires a CUDA GPU for
the intended deployment. This first runtime accepts text or JSON state; HTTP
image decoding is outside the Tetris example scope.

## Test without a model

Install only the server and development dependencies:

```sh
uv sync --group dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Tests inject a fake decision adapter and do not download model weights or use
CUDA.

## Run with CLEF-Flash

Download the complete model repository, including `joint_head.safetensors` and
`joint_schema_model.py`, then start the server with its path:

```sh
uv sync --extra model
MODEL_PATH=/path/to/clef-flash uv run uvicorn \
  clef_server.app:app --host 0.0.0.0 --port 8080
```

`MODEL_PATH` defaults to `/mnt/models/clef-flash`, and `MODEL_DEVICE` defaults
to `cuda`.

The runtime provides the following probes:

- `GET /health/live` reports whether the HTTP process is live.
- `GET /health/ready` returns `200` only after the model has loaded.
