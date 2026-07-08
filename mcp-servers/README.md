# MCP server examples

These examples show how to run MCP servers on prokube with ToolHive.

- [`deploy-upstream-mcp-server`](./deploy-upstream-mcp-server/): deploy an existing upstream MCP server image with a ToolHive `MCPServer` resource.
- [`build-custom-mcp-server`](./build-custom-mcp-server/): build and deploy a small custom FastMCP server image.

Use the prokube **MCP** UI for the normal workflow. These examples are useful when you want to understand the underlying Kubernetes resources, test GitOps-style deployment, or build your own MCP server image.

## Prerequisites

- Access to a prokube workspace with MCP servers enabled.
- A prokube Lab or notebook running in the target workspace.
- `kubectl` configured for the current workspace namespace.
- Permission to create ToolHive `MCPServer` resources in the workspace namespace.
