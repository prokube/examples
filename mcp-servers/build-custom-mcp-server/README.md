# Build and deploy a custom MCP server

This example deploys a FastMCP server for workspace runbooks. It stores Markdown
files on a PVC and uses simple text search without a vector database.

## Tools

The server exposes:

- `list_runbooks`
- `get_runbook`
- `save_runbook`
- `search_runbooks`
- `delete_runbook`

## Image

The example manifest uses an image built from `runbook-server/` by this
repository's `Build Workspace Runbooks MCP Image` GitHub workflow:

```text
europe-west3-docker.pkg.dev/prokube-internal/prokube-customer/workspace-runbooks-mcp:latest
```

The workflow also publishes a `commit-<git-sha>` tag for reproducible
deployments.

## Deploy

```bash
export NAMESPACE="$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace)"
kubectl apply -n "$NAMESPACE" -f workspace-runbooks.yaml

kubectl wait -n "$NAMESPACE" \
  --for=jsonpath='{.status.phase}'=Ready \
  mcpservers.toolhive.stacklok.dev/workspace-runbooks \
  --timeout=180s
```

Wait for the `MCPServer` phase as shown above. Initial image pull and PVC
provisioning can take a short while.

## Connect

Create a Bearer API key for `workspace-runbooks` on the **API Keys** page in the
prokube UI. Copy the external URL from the server's page under **MCP**.

For clients using the `mcpServers` configuration format:

```json
{
  "mcpServers": {
    "workspace-runbooks": {
      "type": "http",
      "url": "https://<your-prokube-domain>/mcp/<workspace>/workspace-runbooks",
      "headers": {
        "Authorization": "Bearer <API_KEY>"
      }
    }
  }
}
```

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
