# kagent examples

These examples introduce [kagent](https://kagent.dev/) agents on prokube one
step at a time:

1. [`basic-agent`](./basic-agent/) creates an agent without tools.
2. [`agent-with-mcp`](./agent-with-mcp/) gives an agent a workspace MCP tool.
3. [`multi-agent`](./multi-agent/) delegates web research to a second agent.
4. [`a2a-client`](./a2a-client/) calls an agent from outside the cluster with
   an API key.
5. [`github-agent`](./github-agent/) runs code in its own sandboxes and calls
   the GitHub API with a token it never sees.
6. [`tracing`](./tracing/) sends an agent's traces to MLflow.

Each example works in the **Agents** page of the prokube UI or with `kubectl`.
The `kubectl` steps run from a prokube Lab terminal; from another terminal, add
`-n <workspace>` to each command.

## How agents are built

- **AgentTemplate**: what the agent does: model, instructions and tools.
- **Harness**: what it runs on. `default` is the kagent runtime on the
  workspace's sandbox workers.
- **Agent**: one template on one harness. Every conversation runs in its own
  isolated sandbox.
- **ModelConfig**: a model. Models an administrator grants through the AI
  Gateway appear in every workspace with origin **AI Gateway** and need no key.

Agents have no shell of their own. To let an agent run code, turn on **Run
code**; the code then runs in separate sandboxes, as in
[`github-agent`](./github-agent/).
