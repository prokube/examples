# Build a LangGraph BYO agent

This example packages a custom
[LangGraph](https://docs.langchain.com/oss/python/langgraph/overview) workflow
as a kagent BYO agent. The agent researches the prokube website and returns a
concise summary that includes the source URL. It demonstrates how to bring a
custom, deterministic workflow into kagent when a declarative agent does not
provide enough control.

Unlike the declarative agents in the earlier examples, the workflow controls
every processing step:

1. Validate that the request contains a `https://prokube.ai` URL.
2. Fetch and extract readable page text without an LLM call.
3. Ask Claude for a one-sentence summary with a source URL.
4. Validate the response and revise it once only when necessary.

The URL allowlist and redirect checks make the deliberately small fetcher safe
to expose as an example. Extend the allowlist only together with equivalent
network controls.

## Prerequisites

kagent must be enabled on your prokube cluster, and you need an Anthropic API
key. If `kubectl apply` fails with the following error, kagent is not installed
and you need to ask your platform admin to enable it:

```text
no matches for kind "Agent" in version "kagent.dev/v1alpha2"
ensure CRDs are installed first
```

## Run the notebook

The easiest way to try the example is
[`langgraph-researcher.ipynb`](./langgraph-researcher.ipynb). Open it in a
prokube Lab and run its cells. It creates the credentials, deploys the agent
from the prebuilt image, sends it a request from the Lab and with an API key,
and cleans up.

If you prefer a terminal, follow the steps below instead. They run from a
prokube Lab terminal and use its current workspace namespace. From another
terminal, add `-n <workspace>` to each `kubectl` command.

## Create the credentials

Create the Anthropic secret if it does not exist:

```bash
kubectl create secret generic anthropic-api-key \
  --from-literal=ANTHROPIC_API_KEY='<your-anthropic-api-key>'
```

## Image

`agent.yaml` uses a prebuilt image, so you can deploy the example as is:

```text
europe-west3-docker.pkg.dev/prokube/releases/langgraph-researcher:v1.0.1
```

If you change the workflow, follow [Build your own image](#build-your-own-image)
below and update `agent.yaml` with your image.

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

## Build your own image

After changing the workflow, run these commands from this example's directory
in a prokube Lab terminal. Labs use the `pk-builder` remote BuildKit service and
do not require a local Docker daemon:

```bash
export IMAGE=<registry>/<project>/langgraph-researcher:0.1.0
docker login <registry>
docker buildx build \
  --builder pk-builder \
  --platform linux/amd64 \
  --push \
  -t "$IMAGE" \
  langgraph-researcher
```

Replace `byo.deployment.image` in `agent.yaml` with the pushed image. Add
registry credentials to the workspace first when the image is private.

## Use another model provider

The workflow calls Claude through `ChatAnthropic` in
[`agent.py`](./langgraph-researcher/agent.py). Unlike the declarative agents, it
does not use a ModelConfig. To use another provider, for example OpenAI:

1. Replace `ChatAnthropic` with `ChatOpenAI` from `langchain-openai` and set a
   model your account can use. For an OpenAI-compatible endpoint, such as a
   self-hosted vLLM model, also pass its `base_url`.
2. Replace `langchain-anthropic` with `langchain-openai` in `requirements.txt`.
3. Build and push your own image as described above.
4. In `agent.yaml`, replace the `ANTHROPIC_API_KEY` variable with
   `OPENAI_API_KEY` from a Secret holding your OpenAI key.
