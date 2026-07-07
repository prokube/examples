# Build and deploy a custom MCP server

This example builds a small FastMCP server for workspace-specific operational runbooks.

The server stores Markdown files in `/data/runbooks`, which is backed by a PVC in `workspace-runbooks.yaml`. It does not use RAG, embeddings, or a vector database. Search is simple case-insensitive text matching over Markdown files.

The example demonstrates:

- a readable custom MCP server implementation;
- a non-root container image;
- read-only root filesystem compatibility;
- persistent workspace data;
- seeding initial Markdown files into the PVC on first start.

## Tools

The server exposes:

- `list_runbooks`
- `get_runbook`
- `save_runbook`
- `search_runbooks`
- `delete_runbook`

## How runbooks get into the server

There are two paths:

- Seed files in `runbook-server/seed-runbooks/` are copied into `/data/runbooks` when the server starts and the PVC is empty.
- MCP clients can create or update runbooks later with the `save_runbook` tool.

Because `/data` is backed by a PVC, runbooks created through MCP tools survive pod restarts.

## Build and push the image

```bash
export IMAGE=<registry>/<project>/workspace-runbooks-mcp:0.1.0
docker build -t "$IMAGE" runbook-server
docker push "$IMAGE"
```

## Deploy

Replace `IMAGE_PLACEHOLDER` with the pushed image and apply the manifest:

```bash
sed "s|IMAGE_PLACEHOLDER|$IMAGE|g" workspace-runbooks.yaml | kubectl apply -n "$NAMESPACE" -f -
kubectl get mcpservers.toolhive.stacklok.dev -n "$NAMESPACE"
```

After the server is running, open **MCP** in the prokube UI and copy the server URL from the deployed servers table or details page.

## Clean up

```bash
sed "s|IMAGE_PLACEHOLDER|$IMAGE|g" workspace-runbooks.yaml | kubectl delete -n "$NAMESPACE" -f -
```
