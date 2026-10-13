# Deploy a basic agent

This example deploys a simple [kagent](https://kagent.dev/) agent without tools.
The agent references a `ModelConfig`, so its configuration is independent of the
model provider.

The examples and notebooks use Anthropic Claude. To use OpenAI, a self-hosted
model, or another provider, edit the manifests as described in
[Use another model provider](#use-another-model-provider).

## Prerequisites

kagent must be enabled on your prokube cluster, and you need an Anthropic API
key. If `kubectl apply` fails with the following error, kagent is not installed
and you need to ask your platform admin to enable it:

```text
no matches for kind "ModelConfig" in version "kagent.dev/v1alpha2"
ensure CRDs are installed first
```

## Run the notebook

The easiest way to try the example is
[`basic-agent.ipynb`](./basic-agent.ipynb). Open it in a prokube Lab and run its
cells.

If you prefer a terminal, follow the steps below instead. They run from a
prokube Lab terminal and use its current workspace namespace. From another
terminal, add `-n <workspace>` to each `kubectl` command.

## Create the credentials

With `ANTHROPIC_API_KEY` set to your API key, create the Secret. The label shows
it under **K8s Secrets** in the prokube user menu.

```bash
kubectl create secret generic anthropic-api-key \
  --from-literal=ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY"
kubectl label secret anthropic-api-key prokube.ai/user-secret=true
```

You can create the same Secret under **K8s Secrets** in the prokube user menu
instead. Use `anthropic-api-key` as its name and `ANTHROPIC_API_KEY` as the key.
See [Kubernetes
Secrets](https://prokube.ai/docs/1.9/platform/kubernetes.html#kubernetes-secrets).

## Deploy

Create the ModelConfig:

```bash
kubectl apply -f anthropic-model.yaml
kubectl wait --for=condition=Accepted \
  modelconfigs.kagent.dev/anthropic-haiku --timeout=2m
```

Create the agent:

```bash
kubectl apply -f assistant.yaml
kubectl wait --for=condition=Ready \
  agents.kagent.dev/simple-assistant --timeout=3m
```

## Connect

After the agent reaches `Ready`, open the [Agents page](/pkui/kagent) in the
prokube UI (`https://<your-prokube-domain>/pkui/kagent`), select
`simple-assistant`, and start a chat.

From a Lab in the workspace, send a message through the internal Agent Gateway
route without an API key:

```bash
export A2A_URL=http://agentgateway-proxy.agentgateway-system.svc.cluster.local/_platform/a2a/$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace)/simple-assistant

a2a() {
  curl -sS "$A2A_URL" "${@:2}" \
    -H 'Content-Type: application/json' \
    --data "$(jq -n --arg text "$1" '{jsonrpc: "2.0", id: "1", method: "message/send",
      params: {message: {role: "user", messageId: "message-1", parts: [{kind: "text", text: $text}]}}}')" \
    | jq -r '.result.artifacts[0].parts[0].text'
}

a2a 'What can you help me with?'
```

`a2a` sends one A2A `message/send` request with the given text and prints the
agent's answer. It passes further arguments to `curl`, so add `-v` to debug a
request.

From outside the cluster, create a Bearer API key for `simple-assistant` on the
[API Keys page](/pkui/ai-gateway/keys) in the prokube UI
(`https://<your-prokube-domain>/pkui/ai-gateway/keys`). Then point `a2a` at the
agent's external route and pass the key:

```bash
export A2A_URL=https://<your-prokube-domain>/svc/a2a/<workspace>/simple-assistant
a2a 'What can you help me with?' -H 'Authorization: Bearer <API_KEY>'
```

## Clean up

Delete the agent:

```bash
kubectl delete -f assistant.yaml
```

The later examples reuse the ModelConfig and Secret. If you do not continue with
[`agent-with-mcp`](../agent-with-mcp/), delete them too:

```bash
kubectl delete -f anthropic-model.yaml
kubectl delete secret anthropic-api-key
```

Delete any API key created for external access on the [API Keys
page](/pkui/ai-gateway/keys).

## Use another model provider

Agents reference a ModelConfig by name. To switch the provider, create another
ModelConfig as described below, then point the agents at it as described in
[Point the agents at your ModelConfig](#point-the-agents-at-your-modelconfig).

### OpenAI or an OpenAI-compatible endpoint

Store the API key in a Secret:

```bash
kubectl create secret generic openai-api-key \
  --from-literal=OPENAI_API_KEY='<your-openai-api-key>'
kubectl label secret openai-api-key prokube.ai/user-secret=true
```

Save a ModelConfig that uses it as `openai-model.yaml`:

```yaml
apiVersion: kagent.dev/v1alpha2
kind: ModelConfig
metadata:
  name: openai-model
spec:
  provider: OpenAI
  model: <openai-model-name>
  apiKeySecret: openai-api-key
  apiKeySecretKey: OPENAI_API_KEY
```

Apply it:

```bash
kubectl apply -f openai-model.yaml
```

For an OpenAI-compatible endpoint, such as a self-hosted vLLM model, keep
`provider: OpenAI` and add its URL under `spec.openAI.baseUrl`.

### A model from prokube LLM Serving

Models deployed on the [LLM Serving page](/pkui/llm) in the prokube UI
(`https://<your-prokube-domain>/pkui/llm`) need no Secret. On the
[Agents page](/pkui/kagent), create an **Internal - OpenAI-compatible**
ModelConfig and select the model. See
[Choose or Create a Model Configuration](https://prokube.ai/docs/1.9/agentops/agents.html#_2-choose-or-create-a-model-configuration).

The agents in [`agent-with-mcp`](../agent-with-mcp/) and
[`multi-agent`](../multi-agent/) call tools, so enable automatic tool calling
when you deploy the model. Presets that support it enable it and select the
tool-call parser for you. See
[Enable Tool Calling for Agents](https://prokube.ai/docs/1.9/agentops/llm_serving.html#enable-tool-calling-for-agents).

### Other providers

See the kagent
[supported providers](https://kagent.dev/docs/kagent/0.x/supported-providers/)
for Azure OpenAI, Gemini, Vertex AI, Bedrock, Ollama, and others. The agents in
the later examples call tools, so choose a model that supports tool calling.

### Point the agents at your ModelConfig

Replace `modelConfig: anthropic-haiku` with the name of your ModelConfig, for
example `modelConfig: openai-model`, in:

- [`assistant.yaml`](./assistant.yaml)
- [`web-researcher.yaml`](../agent-with-mcp/web-researcher.yaml)
- [`research-coordinator.yaml`](../multi-agent/research-coordinator.yaml)

Then apply each changed manifest again, for example
`kubectl apply -f assistant.yaml`. The notebooks always use Anthropic, so follow the terminal steps instead.
