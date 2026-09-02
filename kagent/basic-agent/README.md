# Deploy a basic agent

This example deploys a simple [kagent](https://kagent.dev/) agent without tools.
The agent references a `ModelConfig`, so its configuration is independent of the
model provider.

The included ModelConfig uses Anthropic Claude as a concrete example. The same
pattern works with an existing model granted by an administrator, a self-hosted
model, or another external provider, including OpenAI-compatible models.

The commands below run from a prokube Lab terminal and use its current workspace
namespace. From another terminal, add `-n <workspace>` to each `kubectl` command.

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
curl -sS http://agentgateway-proxy.agentgateway-system.svc.cluster.local/_platform/a2a/<workspace>/simple-assistant \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"1","method":"message/send","params":{"message":{"role":"user","parts":[{"kind":"text","text":"What can you help me with?"}],"messageId":"message-1"}}}' |
  jq -r '.result.artifacts[0].parts[0].text'
```

From outside the cluster, create a Bearer API key for `simple-assistant` on
the **API Keys** page. Then use its external route:

```bash
curl -sS https://<your-prokube-domain>/a2a/<workspace>/simple-assistant \
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
