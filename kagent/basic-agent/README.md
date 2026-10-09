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
cells. It creates the credentials, deploys the agent, sends it a message from
the Lab and with an API key, and cleans up.

If you prefer a terminal, follow the steps below instead. They run from a
prokube Lab terminal and use its current workspace namespace. From another
terminal, add `-n <workspace>` to each `kubectl` command.

## Create the credentials

Replace the placeholder in `anthropic-secret.yaml` with your API key, then
apply it. Do not commit the key.

```bash
kubectl apply -f anthropic-secret.yaml
```

You can create the same Secret from the **Secrets** page in the prokube UI
instead. Use `anthropic-api-key` as its name and `ANTHROPIC_API_KEY` as the key.

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

After the agent reaches `Ready`, open **Agents** in the prokube UI, select
`simple-assistant`, and start a chat.

From a Lab in the workspace, send a message through the internal Agent Gateway
route without an API key:

```bash
curl -sS http://agentgateway-proxy.agentgateway-system.svc.cluster.local/_platform/a2a/$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace)/simple-assistant \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"1","method":"message/send","params":{"message":{"role":"user","parts":[{"kind":"text","text":"What can you help me with?"}],"messageId":"message-1"}}}' |
  jq -r '.result.artifacts[0].parts[0].text'
```

From outside the cluster, create a Bearer API key for `simple-assistant` on
the **API Keys** page at `https://<your-prokube-domain>/pkui/ai-gateway/keys`.
Then use its external route:

```bash
curl -sS https://<your-prokube-domain>/svc/a2a/<workspace>/simple-assistant \
  -H 'Authorization: Bearer <API_KEY>' \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"1","method":"message/send","params":{"message":{"role":"user","parts":[{"kind":"text","text":"What can you help me with?"}],"messageId":"message-1"}}}' |
  jq -r '.result.artifacts[0].parts[0].text'
```

## Clean up

```bash
kubectl delete -f assistant.yaml
kubectl delete -f anthropic-model.yaml
kubectl delete -f anthropic-secret.yaml
```

Delete any API key created for external access from the prokube UI.

## Use another model provider

Agents only reference a ModelConfig by name, so switching the provider means
creating a different Secret and ModelConfig and pointing the agents at it. For
example, for OpenAI:

```bash
kubectl create secret generic openai-api-key \
  --from-literal=OPENAI_API_KEY='<your-openai-api-key>'
```

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

For an OpenAI-compatible endpoint, such as a self-hosted vLLM model, keep
`provider: OpenAI` and add its URL under `spec.openAI.baseUrl`. Agents with
tools need a model that supports tool calling.

Then replace `modelConfig: anthropic-haiku` with `modelConfig: openai-model` in
`assistant.yaml` and, for the later examples, in
[`web-researcher.yaml`](../agent-with-mcp/web-researcher.yaml) and
[`research-coordinator.yaml`](../multi-agent/research-coordinator.yaml). The
notebooks always use Anthropic, so follow the terminal steps instead. See the
kagent [supported providers](https://kagent.dev/docs/kagent/supported-providers)
for Azure OpenAI, Gemini, Vertex AI, Bedrock, Ollama, and others.
