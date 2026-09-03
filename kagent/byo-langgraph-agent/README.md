# Build a LangGraph BYO agent

This example packages a custom
[LangGraph](https://docs.langchain.com/oss/python/langgraph/overview) workflow
as a kagent BYO agent. Unlike the declarative agents in the earlier examples,
the workflow controls every processing step:

1. Validate that the request contains a `https://prokube.ai` URL.
2. Fetch and extract readable page text without an LLM call.
3. Ask Claude for a one-sentence summary with a source URL.
4. Validate the response and revise it once only when necessary.

The URL allowlist and redirect checks make the deliberately small fetcher safe
to expose as an example. Extend the allowlist only together with equivalent
network controls.

The commands below run from a prokube Lab terminal and use its current workspace
namespace. From another terminal, add `-n <workspace>` to each `kubectl` command.

## Prerequisites

- kagent and its BYO agent support are installed on the cluster.
- `regcred-prokube` can pull from the configured Artifact Registry repository.
- `anthropic-api-key` contains the key `ANTHROPIC_API_KEY` in the workspace.

Create the Anthropic secret if it does not exist:

```bash
kubectl create secret generic anthropic-api-key \
  --from-literal=ANTHROPIC_API_KEY='<your-anthropic-api-key>'
```

## Build

The repository workflow `.github/workflows/langgraph-researcher.yaml` publishes
both `latest` and immutable `commit-<sha>` tags. Run it with GitHub Actions, or
build the image locally for development:

```bash
docker build --platform linux/amd64 \
  -t europe-west3-docker.pkg.dev/prokube-internal/prokube-customer/langgraph-researcher:latest \
  ./langgraph-researcher
docker push europe-west3-docker.pkg.dev/prokube-internal/prokube-customer/langgraph-researcher:latest
```

For reproducible deployments, replace the `latest` tag in `agent.yaml` with the
workflow's `commit-<sha>` tag.

## Deploy

```bash
kubectl apply -f agent.yaml
kubectl wait --for=condition=Ready \
  agents.kagent.dev/langgraph-researcher --timeout=3m
```

## Try it

Open **Agents** in the prokube UI, select `langgraph-researcher`, and ask:

```text
Research https://prokube.ai and summarize what prokube offers in one sentence.
Include the source URL.
```

The final response should contain one concise summary and
`Source: https://prokube.ai`.

## Clean up

```bash
kubectl delete -f agent.yaml
kubectl delete secret anthropic-api-key
```

Keep the secret if another agent in the workspace uses it.
