# Sandbox examples

prokube sandboxes are isolated environments for agents and their code that
start and resume in well under a second. These examples use them with the
[prokube SDK and `pk` CLI](https://github.com/prokube/prokube-sdk):

- [`parallel-sandboxes`](./parallel-sandboxes/) runs a test in 20 sandboxes
  at once.
- [`langgraph-data-analysis`](./langgraph-data-analysis/) gives a LangGraph
  agent sandbox tools built on the SDK.
- [`mcp-server`](./mcp-server/) gives agents the same tools over MCP, in the
  workspace and on a laptop.
- [`claude-code-worker`](./claude-code-worker/) runs Claude Code headless in a
  sandbox, with the API key injected at egress.
- [`opencode-server`](./opencode-server/) runs an opencode server in a
  sandbox and attaches to it from a laptop.

The notebooks run in a prokube Lab with sandbox access: when you create the
Lab, enable **Allow access to sandboxes** under **Configurations**. There the
SDK and `pk` need no login. On a laptop, install the SDK with its CLI and log
in once:

```bash
pip install 'prokube-sdk[cli] @ git+https://github.com/prokube/prokube-sdk@v1.0.0'
pk auth login https://<your-prokube-domain> --workspace <workspace>
```

See [Sandboxes](https://prokube.ai/docs/development/agentops/sandboxes.html)
in the prokube docs for presets, network rules and credentials.
