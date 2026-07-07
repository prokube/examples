# MCP servers with ToolHive

This example shows two ways to run MCP servers on prokube with ToolHive:

- deploy an existing upstream MCP server image with a ToolHive `MCPServer` resource;
- build and deploy a small custom MCP server image for workspace runbooks.

Use the prokube **MCP** UI for the normal workflow. These manifests are useful when you want to understand the generated Kubernetes resources, test GitOps-style deployment, or build your own MCP server image.

## Prerequisites

- Access to a prokube workspace with MCP servers enabled.
- `kubectl` configured for the target workspace.
- Permission to create ToolHive `MCPServer` resources in the workspace namespace.
- A container registry for the custom image example.

Set your workspace namespace:

```bash
export NAMESPACE=<workspace-namespace>
```

## Deploy the upstream time server

The `time-server.yaml` manifest runs the upstream Time MCP server image from the MCP registry.

```bash
kubectl apply -n "$NAMESPACE" -f time-server.yaml
kubectl get mcpservers.toolhive.stacklok.dev -n "$NAMESPACE"
```

The server exposes the `get_current_time` and `convert_time` tools.

Note: the current upstream image requires root because of its image layout. Use this as a minimal ToolHive example, not as a production baseline.

## Build the custom runbook server

The `runbook-server/` directory contains a small FastMCP server for workspace-specific operational runbooks. It stores Markdown files in `/data/runbooks`, which is backed by a PVC in the example manifest.

It exposes:

- `list_runbooks`
- `get_runbook`
- `save_runbook`
- `search_runbooks`
- `delete_runbook`

Build and push the image:

```bash
export IMAGE=<registry>/<project>/workspace-runbooks-mcp:0.1.0
docker build -t "$IMAGE" runbook-server
docker push "$IMAGE"
```

Update `custom-fastmcp-server.yaml` and replace `IMAGE_PLACEHOLDER` with the pushed image:

```bash
sed "s|IMAGE_PLACEHOLDER|$IMAGE|g" custom-fastmcp-server.yaml | kubectl apply -n "$NAMESPACE" -f -
kubectl get mcpservers.toolhive.stacklok.dev -n "$NAMESPACE"
```

The custom image runs as a non-root user and does not require a writable root filesystem. Runbook data is written to the mounted `/data` volume.

## Connect a client

After the server is running, open **MCP** in the prokube UI and copy the server URL from the deployed servers table or details page.

For external clients, create an API key scoped to the MCP server and use the authentication format expected by the client. Existing MCP examples commonly use the `x-api-key` header.

## Clean up

```bash
kubectl delete -n "$NAMESPACE" -f time-server.yaml
sed "s|IMAGE_PLACEHOLDER|$IMAGE|g" custom-fastmcp-server.yaml | kubectl delete -n "$NAMESPACE" -f -
```
