# Sandbox tools over MCP

`pk sandbox mcp` is the prokube SDK's [MCP](https://modelcontextprotocol.io/)
server for sandboxes. It gives any MCP client the tools `list`, `create`,
`run`, `read_file`, `write_file`, `suspend`, `resume` and `delete`, so an
agent can use sandboxes without tool code of your own. This example deploys it
in a workspace for agents there, and adds it to Claude Code and opencode on a
laptop.

## Prerequisites

MCP servers and sandboxes must be enabled on your prokube cluster.

## How it works

- [`sandbox-mcp.yaml`](./sandbox-mcp.yaml) runs `pk sandbox mcp` as a
  ToolHive `MCPServer` that serves streamable HTTP. Like every MCP server in
  the workspace, it appears on the **MCP** page of the prokube UI and behind
  Agent Gateway.
- The server runs as the workspace's ServiceAccount `default-editor`, and the
  label `access-sandboxes: "true"` gives it a token for sandboxes. Every
  caller therefore acts as the workspace, on the workspace's sandboxes only.
  Who may call the server is decided by Agent Gateway, as for every MCP
  server: workloads in the workspace through the internal route, external
  clients with an API key for `sandbox`.
- Each tool is one SDK call. Errors come back as text the agent can act on;
  for example, an unknown preset lists the available ones.

## Run the notebook

Open [`sandbox-mcp.ipynb`](./sandbox-mcp.ipynb) in a prokube Lab and run its
cells. A [Pydantic AI](https://ai.pydantic.dev/) agent creates a sandbox,
writes and tests a small function in it and deletes it, all through the
server.

## Use it on a laptop

Locally, `pk sandbox mcp` speaks stdio and uses your login:

```bash
pip install 'prokube-sdk[cli] @ git+https://github.com/prokube/prokube-sdk@sandboxv3/main'
pk login https://<your-prokube-domain> --workspace <workspace>
```

Claude Code:

```bash
claude mcp add sandbox -- pk sandbox mcp
```

opencode, in `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "sandbox": { "type": "local", "command": ["pk", "sandbox", "mcp"] }
  }
}
```

Then ask, for example: `Create a sandbox named demo, run uname -a in it and
delete it.`

## Clean up

```bash
kubectl delete -f sandbox-mcp.yaml
```

The agent deletes its sandbox. If it stopped before, delete it on the
**Sandboxes** page of the prokube UI or with `pk sandbox delete mcp-demo`.
