# Sandbox tools over MCP

`pk sandbox mcp` is the prokube SDK's [MCP](https://modelcontextprotocol.io/)
server for sandboxes. It gives any MCP client the tools `list`, `create`,
`run`, `read_file`, `write_file`, `suspend`, `resume`, `revert` and `delete`,
so an agent can use sandboxes without tool code of your own. This example deploys it
in a workspace for agents there, and adds it to Claude Code and opencode on a
laptop.

## Prerequisites

MCP servers and sandboxes must be enabled on your prokube cluster. If
`kubectl apply` fails with the following error, ToolHive is not installed and
you need to ask your platform admin to enable MCP servers:

```text
no matches for kind "MCPServer" in version "toolhive.stacklok.dev/v1beta1"
ensure CRDs are installed first
```

## How it works

- [`sandbox-mcp.yaml`](./sandbox-mcp.yaml) runs `pk sandbox mcp` as a
  ToolHive `MCPServer` that serves streamable HTTP. Like every MCP server in
  the workspace, it appears on the **MCP** page of the prokube UI and behind
  Agent Gateway.
- The server runs as the workspace's ServiceAccount `default-editor`, so every
  caller acts as the workspace, on its sandboxes only, and Agent Gateway
  decides who may call it, as for every MCP server.

## Run the notebook

Open [`sandbox-mcp.ipynb`](./sandbox-mcp.ipynb) in a prokube Lab and run its
cells: a [Pydantic AI](https://ai.pydantic.dev/) agent creates, uses and
deletes a sandbox, all through the server.

## Use it on a laptop

Locally, `pk sandbox mcp` speaks stdio and uses your login; install the `pk`
CLI and log in as described in the [sandbox examples](../README.md).

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
