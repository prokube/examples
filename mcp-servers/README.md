# MCP server examples

These examples show how to run MCP servers on prokube with ToolHive.

- [`deploy-upstream-mcp-server`](./deploy-upstream-mcp-server/): deploy an existing upstream MCP server image with a ToolHive `MCPServer` resource.
- [`build-custom-mcp-server`](./build-custom-mcp-server/): build and deploy a small custom FastMCP server image.

Use the prokube **MCP** UI for the normal workflow. These examples are useful when you want to understand the underlying Kubernetes resources, test GitOps-style deployment, or build your own MCP server image.

## Prerequisites

- Access to a prokube workspace with MCP servers enabled.
- `kubectl` configured for the target workspace.
- Permission to create ToolHive `MCPServer` resources in the workspace namespace.

Set your workspace namespace:

```bash
export NAMESPACE=<workspace-namespace>
```

For external MCP clients, create an API key scoped to the deployed MCP server and use the authentication format expected by the client. Existing MCP examples commonly use the `x-api-key` header.
