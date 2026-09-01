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

## Use the prepared image

The example manifest uses an image built from `runbook-server/` by this
repository's `Build Workspace Runbooks MCP Image` GitHub workflow:

```text
europe-west3-docker.pkg.dev/prokube-internal/prokube-customer/workspace-runbooks-mcp:latest
```

The workflow also publishes an immutable `commit-<git-sha>` tag. Pin that tag in
the manifest when you need a reproducible deployment. The ToolHive backend uses
its own ServiceAccount, so the manifest explicitly attaches the workspace's
`regcred-prokube` pull secret for this prepared private image.

## Deploy

```bash
export NAMESPACE="$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace)"
kubectl apply -n "$NAMESPACE" -f workspace-runbooks.yaml

kubectl wait -n "$NAMESPACE" \
  --for=jsonpath='{.status.phase}'=Ready \
  mcpservers.toolhive.stacklok.dev/workspace-runbooks \
  --timeout=180s
```

The initial image pull and PVC provisioning can take a short while. Wait for the
ToolHive `MCPServer` phase as shown above rather than relying only on Pod
readiness. After a manual backend Pod restart, the MCP proxy may briefly return
`503` while it reconnects; retry after a few seconds.

After the server is running, open **MCP** in the prokube UI. Use the included
[`mcp-client.py`](../mcp-client.py) to list or call tools as shown in the parent
[MCP server examples](../README.md) guide.

## Build your own image

Build your own image after changing the server. Managed prokube Labs use a
remote BuildKit service and do not run a local Docker daemon, so build and push
in one operation:

```bash
export IMAGE=<registry>/<project>/workspace-runbooks-mcp:0.1.0
docker login <registry>
docker buildx build --push -t "$IMAGE" runbook-server
```

Replace the `spec.image` value in `workspace-runbooks.yaml` with your pushed
image. Add registry credentials to the workspace before deployment when the
image is private.

## Clean up

```bash
kubectl delete -n "$NAMESPACE" -f workspace-runbooks.yaml
```

The PVC is part of the manifest and is deleted by this command. Export any
runbooks you want to retain before cleanup.
