# MCP server examples

This directory contains two examples:

- [`deploy-upstream-mcp-server`](./deploy-upstream-mcp-server/) deploys an
  existing Fetch MCP server image.
- [`build-custom-mcp-server`](./build-custom-mcp-server/) builds and deploys a
  small FastMCP server with persistent Markdown notes.

Each example has a notebook to run in a prokube Lab. Its README also covers
the same steps in a terminal and connecting external MCP clients.

Clients connect through
[Agent Gateway](https://prokube.ai/docs/1.9/agentops/agent_gateway.html#mcp-federation-and-tool-selection),
not the server's Kubernetes Service. Once a ToolHive `MCPServer` is deployed,
prokube's controller configures its gateway routes, so no extra setup is
needed.

See [MCP Servers](https://prokube.ai/docs/1.9/agentops/mcp_servers.html) in the
prokube docs for how prokube runs MCP servers and how to manage them in the
prokube UI.
