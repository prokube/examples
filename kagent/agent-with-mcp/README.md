# Give an agent MCP tools

This example adds web access to a kagent agent through MCP. It builds on the
[`basic-agent`](../basic-agent/) example and reuses its ModelConfig.

First deploy the Fetch server from the
[`mcp-servers/deploy-upstream-mcp-server`](../../mcp-servers/deploy-upstream-mcp-server/)
example. prokube then publishes the workspace's MCP tools through the
`gateway-mcp` RemoteMCPServer.

The commands below run from a prokube Lab terminal and use its current workspace
namespace. From another terminal, add `-n <workspace>` to each `kubectl` command.

## Deploy

Wait until kagent has discovered the workspace MCP tools:

```bash
kubectl wait --for=condition=Accepted \
  remotemcpservers.kagent.dev/gateway-mcp --timeout=3m
```

Create the agent:

```bash
kubectl apply -f web-researcher.yaml
kubectl wait --for=condition=Ready \
  agents.kagent.dev/web-researcher --timeout=3m
```

For simplicity, the agent can use all tools published by `gateway-mcp`. Limit
`toolNames` in production when it should only access specific tools.

## Try it

Open **Agents** in the prokube UI, select `web-researcher`, and ask:

```text
Fetch https://example.com and summarize it in one sentence. Include the source
URL.
```

From a Lab in the workspace, inspect the agent without an API key:

```bash
curl -sS \
  http://agentgateway-proxy.agentgateway-system.svc.cluster.local/_platform/a2a/<workspace>/web-researcher/.well-known/agent-card.json
```

From outside the cluster, create a Bearer API key for `web-researcher` on the
**API Keys** page and use the external route:

```bash
curl -sS \
  https://<your-prokube-domain>/a2a/<workspace>/web-researcher/.well-known/agent-card.json \
  -H 'Authorization: Bearer <API_KEY>'
```

## Clean up

```bash
kubectl delete -f web-researcher.yaml
```

This leaves the basic agent, ModelConfig, Secret, and Fetch server unchanged.
