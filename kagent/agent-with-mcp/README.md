# Give an agent MCP tools

This example adds web access to a kagent agent through MCP. It builds on the
[`basic-agent`](../basic-agent/) example and reuses its ModelConfig.

First deploy the Fetch server from the
[`mcp-servers/deploy-upstream-mcp-server`](../../mcp-servers/deploy-upstream-mcp-server/)
example. prokube then publishes the workspace's MCP tools through the
`gateway-mcp` `RemoteMCPServer`. This platform-managed resource connects kagent
to the workspace's internal MCP route; you do not need to create it yourself.

You can instead create your own `RemoteMCPServer` for any MCP endpoint that
kagent can reach. See the upstream
[MCP tools guide](https://kagent.dev/docs/kagent/getting-started/first-mcp-tool/)
for that workflow.

The commands below run from a prokube Lab terminal and use its current workspace
namespace. From another terminal, add `-n <workspace>` to each `kubectl` command.

## Deploy

Wait until kagent has discovered the workspace MCP tools:

```bash
kubectl wait --for=condition=Accepted \
  remotemcpservers.kagent.dev/gateway-mcp --timeout=3m

kubectl get remotemcpservers.kagent.dev gateway-mcp \
  -o jsonpath='{.status.discoveredTools[*].name}{"\n"}'
```

With only the Fetch server deployed, the output includes `fetch`. The agent
manifest uses `toolNames` to grant access to that tool only. If the workspace
contains multiple MCP servers, Agent Gateway may prefix the name; use the exact
name shown by the command above.

Create the agent:

```bash
kubectl apply -f web-researcher.yaml
kubectl wait --for=condition=Ready \
  agents.kagent.dev/web-researcher --timeout=3m
```

## Try it

Open **Agents** in the prokube UI, select `web-researcher`, and ask:

```text
Fetch https://prokube.ai and summarize what prokube offers in one sentence.
Include the source URL.
```

From a Lab in the workspace, send the same request without an API key:

```bash
curl -sS http://agentgateway-proxy.agentgateway-system.svc.cluster.local/_platform/a2a/<workspace>/web-researcher \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"1","method":"message/send","params":{"message":{"role":"user","parts":[{"kind":"text","text":"Fetch https://prokube.ai and summarize what prokube offers in one sentence. Include the source URL."}],"messageId":"message-1"}}}' |
  jq -r '.result.artifacts[0].parts[0].text'
```

From outside the cluster, create a Bearer API key for `web-researcher` on the
**API Keys** page and use the external route:

```bash
curl -sS https://<your-prokube-domain>/a2a/<workspace>/web-researcher \
  -H 'Authorization: Bearer <API_KEY>' \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"1","method":"message/send","params":{"message":{"role":"user","parts":[{"kind":"text","text":"Fetch https://prokube.ai and summarize what prokube offers in one sentence. Include the source URL."}],"messageId":"message-1"}}}' |
  jq -r '.result.artifacts[0].parts[0].text'
```

## Clean up

```bash
kubectl delete -f web-researcher.yaml
```

This leaves the basic agent, ModelConfig, Secret, and Fetch server unchanged.
