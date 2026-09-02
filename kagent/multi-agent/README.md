# Delegate to another agent

This example adds agent-to-agent delegation. It builds on
[`agent-with-mcp`](../agent-with-mcp/): the coordinator invokes the
`web-researcher`, which uses the Fetch MCP server.

The commands below run from a prokube Lab terminal and use its current workspace
namespace. From another terminal, add `-n <workspace>` to each `kubectl` command.

## Deploy

```bash
kubectl apply -f research-coordinator.yaml
kubectl wait --for=condition=Ready \
  agents.kagent.dev/research-coordinator --timeout=3m
```

## Try it

Open **Agents** in the prokube UI, select `research-coordinator`, and ask:

```text
Research https://example.com and summarize it in one sentence. Include the
source URL.
```

The coordinator delegates the request to `web-researcher`, which fetches the
page through MCP.

From a Lab in the workspace, inspect the coordinator without an API key:

```bash
curl -sS \
  http://agentgateway-proxy.agentgateway-system.svc.cluster.local/_platform/a2a/<workspace>/research-coordinator/.well-known/agent-card.json
```

From outside the cluster, create a Bearer API key for `research-coordinator` on
the **API Keys** page and use the external route:

```bash
curl -sS \
  https://<your-prokube-domain>/a2a/<workspace>/research-coordinator/.well-known/agent-card.json \
  -H 'Authorization: Bearer <API_KEY>'
```

## Clean up

```bash
kubectl delete -f research-coordinator.yaml
```

This leaves the agents and resources from the earlier examples unchanged.
