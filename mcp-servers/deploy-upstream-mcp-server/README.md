# Deploy an upstream MCP server

This example uses [ToolHive](https://docs.stacklok.com/toolhive/) to deploy the
upstream [GoFetch server](https://github.com/StacklokLabs/gofetch).
The [MCP](https://modelcontextprotocol.io/) server exposes a `fetch` tool that
retrieves web pages and converts them to Markdown.

## Deploy

From a prokube Lab terminal, use its current namespace:

```bash
kubectl apply -f fetch-server.yaml

kubectl wait \
  --for=jsonpath='{.status.phase}'=Ready \
  mcpservers.toolhive.stacklok.dev/fetch \
  --timeout=180s
```

From a terminal outside a Lab, set the workspace namespace explicitly:

```bash
export NAMESPACE=<workspace>
kubectl apply -n "$NAMESPACE" -f fetch-server.yaml

kubectl wait -n "$NAMESPACE" \
  --for=jsonpath='{.status.phase}'=Ready \
  mcpservers.toolhive.stacklok.dev/fetch \
  --timeout=180s
```

## Connect

From a Lab in the same namespace, test the internal endpoint directly:

```bash
curl -sS http://mcp-fetch-proxy:8080/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}'
```

From outside the cluster, create a Bearer API key for the `fetch` server on the
**API Keys** page in the prokube UI. Copy the external URL from the server's
page under **MCP**.

For clients using the `mcpServers` configuration format:

```json
{
  "mcpServers": {
    "fetch": {
      "type": "http",
      "url": "https://<your-prokube-domain>/mcp/<workspace>/fetch",
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
