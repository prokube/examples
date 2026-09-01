# Build and deploy a custom MCP server

This example builds an [MCP](https://modelcontextprotocol.io/) server with
[FastMCP](https://gofastmcp.com/) and deploys it through
[ToolHive](https://docs.stacklok.com/toolhive/). It stores Markdown notes on a
PVC and lets MCP clients list, read, save, search, and delete them.

The server is deliberately simple: notes are plain files and search is basic
case-insensitive text matching. It uses no database, embeddings, or vector
search.

## Tools

- `list_notes`
- `get_note`
- `save_note`
- `search_notes`
- `delete_note`

## Image

A prebuilt image is available, so you can deploy the example as is:

```text
europe-west3-docker.pkg.dev/prokube-internal/prokube-customer/markdown-notes-mcp:latest
```

If you change the server, follow [Build your own image](#build-your-own-image)
below and update the manifest with your image.

## Deploy

From a prokube Lab terminal, use its current namespace:

```bash
kubectl apply -f markdown-notes.yaml

kubectl wait --for=condition=Ready \
  mcpservers.toolhive.stacklok.dev/markdown-notes --timeout=3m
```

From a terminal outside a Lab, set the workspace namespace explicitly:

```bash
export NAMESPACE=<workspace>
kubectl apply -n "$NAMESPACE" -f markdown-notes.yaml

kubectl wait -n "$NAMESPACE" --for=condition=Ready \
  mcpservers.toolhive.stacklok.dev/markdown-notes --timeout=3m
```

## Connect

From a Lab in the workspace, use the internal Agent Gateway URL without an API
key:

```bash
curl -sS http://agentgateway-proxy.agentgateway-system.svc.cluster.local/_platform/mcp/<workspace> \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}'
```

From outside the cluster, create a Bearer API key for `markdown-notes` on the
**API Keys** page in the prokube UI. Copy the external URL from the server's
page under **MCP**.

For clients using the `mcpServers` configuration format:

```json
{
  "mcpServers": {
    "markdown-notes": {
      "type": "http",
      "url": "https://<your-prokube-domain>/mcp/<workspace>/markdown-notes",
      "headers": {
        "Authorization": "Bearer <API_KEY>"
      }
    }
  }
}
```

## Build your own image

After changing the server, build and push an image from a prokube Lab with its
remote BuildKit service:

```bash
export IMAGE=<registry>/<project>/markdown-notes-mcp:0.1.0
docker login <registry>
docker buildx build --push -t "$IMAGE" markdown-notes-server
```

Replace `spec.image` in `markdown-notes.yaml` with the pushed image. Add
registry credentials to the workspace first when the image is private.

## Clean up

From a Lab:

```bash
kubectl delete -f markdown-notes.yaml
```

From outside a Lab:

```bash
kubectl delete -n "$NAMESPACE" -f markdown-notes.yaml
```

This also deletes the PVC. Export notes you want to retain before cleanup.
