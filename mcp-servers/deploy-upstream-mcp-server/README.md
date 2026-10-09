# Deploy an upstream MCP server

This example uses [ToolHive](https://docs.stacklok.com/toolhive/) to deploy the
upstream [GoFetch server](https://github.com/StacklokLabs/gofetch).
The [MCP](https://modelcontextprotocol.io/) server exposes a `fetch` tool that
retrieves web pages and converts them to Markdown.

## Prerequisites

MCP servers must be enabled on your prokube cluster (v1.9.0 or later). If
`kubectl apply` fails with the following error, ToolHive is not installed and
you need to ask your platform admin to enable MCP servers:

```text
no matches for kind "MCPServer" in version "toolhive.stacklok.dev/v1beta1"
ensure CRDs are installed first
```

## Run the notebook

The easiest way to try the example is
[`fetch-server.ipynb`](./fetch-server.ipynb). Open it in a prokube Lab and run
its cells. It deploys the server, fetches a web page, connects with an API key,
and cleans up.

If you prefer a terminal, follow the steps below instead.

## Deploy

From a prokube Lab terminal, use its current namespace:

```bash
kubectl apply -f fetch-server.yaml

kubectl wait --for=condition=Ready \
  mcpservers.toolhive.stacklok.dev/fetch-example --timeout=3m
```

From a terminal outside a Lab, set the workspace namespace explicitly:

```bash
export NAMESPACE=<workspace>
kubectl apply -n "$NAMESPACE" -f fetch-server.yaml

kubectl wait -n "$NAMESPACE" --for=condition=Ready \
  mcpservers.toolhive.stacklok.dev/fetch-example --timeout=3m
```

## Connect

### From a Lab

Labs reach the workspace's MCP endpoint through the internal Agent Gateway URL
without an API key. This is the same endpoint the prokube UI shows: it
aggregates all MCP servers in the workspace and prefixes each tool with its
server name, so the `fetch` tool becomes `fetch-example_fetch`.

Open an MCP session and keep its ID:

```bash
export MCP_URL=http://agentgateway-proxy.agentgateway-system.svc.cluster.local/_platform/mcp/$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace)

MCP_SESSION=$(curl -sS -D - -o /dev/null "$MCP_URL" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}' \
  | sed -n 's/^mcp-session-id: //Ip' | tr -d '\r')

mcp() {
  curl -sS "$MCP_URL" \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -H "Mcp-Session-Id: $MCP_SESSION" \
    --data "$1" | sed -n 's/^data: //p'
}

mcp '{"jsonrpc":"2.0","method":"notifications/initialized"}'
```

The gateway responds with server-sent events. `mcp` strips the `data: ` prefix
so that `jq` can format the JSON. To debug a request, run its `curl` command
with `-v` and without the pipes.

List the tools available in the workspace. Tools of other MCP servers in the
workspace appear in this list too:

```bash
mcp '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | jq -r '.result.tools[].name'
```

```text
fetch-example_fetch
```

Fetch a page:

```bash
mcp '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"fetch-example_fetch","arguments":{"url":"https://example.com"}}}' \
  | jq -r '.result.content[0].text'
```

```text
This domain is for use in documentation examples without needing permission. ...
```

### From outside the cluster

Create a Bearer API key for the `fetch-example` server on the **API Keys** page in the
prokube UI at `https://<your-prokube-domain>/pkui/ai-gateway/keys`. Copy the
external URL from the server's page under **MCP**.

For clients using the `mcpServers` configuration format:

```json
{
  "mcpServers": {
    "fetch-example": {
      "type": "http",
      "url": "https://<your-prokube-domain>/svc/mcp/<workspace>/fetch-example",
      "headers": {
        "Authorization": "Bearer <API_KEY>"
      }
    }
  }
}
```

## Clean up

From a Lab:

```bash
kubectl delete -f fetch-server.yaml
```

From outside a Lab:

```bash
kubectl delete -n "$NAMESPACE" -f fetch-server.yaml
```
