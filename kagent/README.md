# Deploy a kagent agent

This example deploys a simple [kagent](https://kagent.dev/) agent backed by an
Anthropic Claude model.

A ModelConfig may already exist because an administrator granted access to a
model. It can also point to a self-hosted model or use your own credentials for
an external provider. This example uses an Anthropic API key to keep the setup
self-contained.

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
  agents.kagent.dev/anthropic-assistant --timeout=3m
```

## Connect

Open **Agents** in the prokube UI, select `anthropic-assistant`, and start a
chat.

From a Lab in the workspace, inspect the agent through the internal Agent
Gateway route without an API key:

```bash
curl -sS \
  http://agentgateway-proxy.agentgateway-system.svc.cluster.local/_platform/a2a/<workspace>/anthropic-assistant/.well-known/agent-card.json
```

From outside the cluster, create a Bearer API key for `anthropic-assistant` on
the **API Keys** page. Then use its external route:

```bash
curl -sS \
  https://<your-prokube-domain>/a2a/<workspace>/anthropic-assistant/.well-known/agent-card.json \
  -H 'Authorization: Bearer <API_KEY>'
```

## Clean up

```bash
kubectl delete -f assistant.yaml
kubectl delete -f anthropic-model.yaml
kubectl delete -f anthropic-secret.yaml
```

Delete any API key created for external access from the prokube UI.
