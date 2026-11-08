# Give an agent MCP tools

This example gives an agent web access through MCP. It uses the Fetch server
from [`mcp-servers/deploy-upstream-mcp-server`](../../mcp-servers/deploy-upstream-mcp-server/)
and the model configuration from [`basic-agent`](../basic-agent/).

## How it works

prokube publishes all MCP servers of the workspace to kagent as one tool
server, `gateway-mcp`. [`template.yaml`](./template.yaml) binds that server and
limits the agent to the Fetch tool:

```yaml
tools:
- mcp:
    server:
      kind: RemoteMCPServer
      name: gateway-mcp
    tools:
    - fetch
```

The agent reaches `gateway-mcp` with a workspace key that the platform adds on
the way out; the agent never sees it.

## Deploy

Deploy the Fetch server unless it is already running:

```bash
kubectl apply -f ../../mcp-servers/deploy-upstream-mcp-server/fetch-server.yaml
kubectl wait --for=condition=Ready mcpservers.toolhive.stacklok.dev/fetch-example --timeout=3m
```

kagent lists the new tool within a few minutes:

```bash
kubectl get remotemcpservers.api.kagent.dev gateway-mcp \
  -o jsonpath='{.status.discoveredTools[*].name}{"\n"}'
```

With more than one MCP server in the workspace, tool names carry the server
name, here `fetch-example_fetch`. Use the name shown above in `template.yaml`.

In the UI, create the agent and select the Fetch tool under **Tools**. With
`kubectl`:

```bash
sed 's/MODEL_CONFIG/<model-config>/' template.yaml | kubectl apply -f -
kubectl apply -f agent.yaml
kubectl wait --for=condition=Ready agent.api.kagent.dev/web-researcher --timeout=5m
```

## Try it

Open `web-researcher` on the **Agents** page and ask:

```text
Fetch https://prokube.ai and summarize what prokube offers in one sentence.
Include the source URL.
```

The chat shows the tool call and its result.

## Clean up

Skip this if you continue with [`multi-agent`](../multi-agent/), which reuses
`web-researcher`.

```bash
kubectl delete -f agent.yaml -f template.yaml
```
