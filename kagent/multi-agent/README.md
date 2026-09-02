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
Research https://prokube.ai and summarize what prokube offers in one sentence.
Include the source URL.
```

The coordinator delegates the request to `web-researcher`, which fetches the
page through MCP.

From a Lab in the workspace, send the same request without an API key:

```bash
curl -sS http://agentgateway-proxy.agentgateway-system.svc.cluster.local/_platform/a2a/<workspace>/research-coordinator \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"1","method":"message/send","params":{"message":{"role":"user","parts":[{"kind":"text","text":"Research https://prokube.ai and summarize what prokube offers in one sentence. Include the source URL."}],"messageId":"message-1"}}}' |
  jq -r '.result.artifacts[0].parts[0].text'
```

From outside the cluster, create a Bearer API key for `research-coordinator` on
the **API Keys** page and use the external route:

```bash
curl -sS https://<your-prokube-domain>/a2a/<workspace>/research-coordinator \
  -H 'Authorization: Bearer <API_KEY>' \
  -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":"1","method":"message/send","params":{"message":{"role":"user","parts":[{"kind":"text","text":"Research https://prokube.ai and summarize what prokube offers in one sentence. Include the source URL."}],"messageId":"message-1"}}}' |
  jq -r '.result.artifacts[0].parts[0].text'
```

## Clean up

```bash
kubectl delete -f research-coordinator.yaml
```

This leaves the agents and resources from the earlier examples unchanged.
