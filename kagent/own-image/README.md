# Run your own agent image

This example runs a [LangGraph](https://docs.langchain.com/oss/python/langgraph/overview)
workflow in your own container image instead of the built-in agent runtime.
The workflow is fixed code, not a model deciding what to do: it takes the URL
from your message, fetches the page, and asks the model for a one-sentence
summary.

## Prerequisites

- Agents are enabled for your workspace (the **Agents** page is available).
- A model configuration in the workspace, for example one granted through the
  AI Gateway. Its name goes into `MODEL_CONFIG` below.
- Docker to build the image, and a registry the agent workers can pull from:
  a public one, or a private one your administrator has allowed for agent
  images.

## How it works

- [`langgraph-researcher/agent.py`](./langgraph-researcher/agent.py) is the
  LangGraph graph. It reads the model from the configuration the platform
  passes in, so the API key never reaches the image.
- [`langgraph-researcher/server.py`](./langgraph-researcher/server.py) serves
  the graph the way the platform expects: it loads its configuration at
  startup, answers on gRPC, and stores tasks in the platform.
  It uses the `kagent-core` and `kagent-langgraph` packages. Their versions must
  match the platform's kagent version (`1.0.0rc3` here).
- [`harness.yaml`](./harness.yaml) runs the image. The image must be pinned by
  digest. [`template.yaml`](./template.yaml) names the model.
- [`network.yaml`](./network.yaml) allows `https://prokube.ai`. The agent can
  reach its model and this host, nothing else.

## Build

```bash
docker build --platform linux/amd64 -t <registry>/langgraph-researcher:v1 ./langgraph-researcher
docker push <registry>/langgraph-researcher:v1
docker buildx imagetools inspect <registry>/langgraph-researcher:v1 --format '{{.Name}}@{{.Manifest.Digest}}'
```

## Deploy

Replace `IMAGE` with the digest reference printed above and `MODEL_CONFIG`
with the model's name:

```bash
sed 's|IMAGE|<registry>/langgraph-researcher@sha256:<digest>|' harness.yaml | kubectl apply -f -
sed 's/MODEL_CONFIG/<model-config>/' template.yaml | kubectl apply -f -
kubectl apply -f network.yaml -f agent.yaml
kubectl wait --for=condition=Ready agent.api.kagent.dev/langgraph-researcher --timeout=5m
```

## Try it

Open `langgraph-researcher` on the **Agents** page and ask:

> Summarize https://prokube.ai

The answer is one sentence followed by `Source: https://prokube.ai`. Asking for
`https://example.com` fails: that host is not allowed.

## Clean up

```bash
kubectl delete -f agent.yaml -f network.yaml -f template.yaml -f harness.yaml
```
