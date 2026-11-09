# kagent examples

These examples show what agents on prokube can do, one step at a time. They
build on each other; each one adds a single new capability.

| | Example | What it shows |
|---|---|---|
| 1 | [`basic-agent`](./basic-agent/) | An agent with a model and instructions |
| 2 | [`agent-with-mcp`](./agent-with-mcp/) | Tools from the workspace's MCP servers |
| 3 | [`run-code`](./run-code/) | Running Python in sandboxes instead of in the agent |
| 4 | [`allowed-hosts`](./allowed-hosts/) | An agent that may reach three hosts and nothing else |
| 5 | [`injected-credentials`](./injected-credentials/) | Logging in to an API with a password the agent never sees |
| 6 | [`harnesses`](./harnesses/) | Agents on Claude Code and Codex instead of the kagent runtime |
| 7 | [`own-image`](./own-image/) | A LangGraph workflow in your own container image |
| 8 | [`multi-agent`](./multi-agent/) | Delegating work to another agent |
| 9 | [`a2a-client`](./a2a-client/) | Calling an agent from your code with an API key |
| 10 | [`tracing`](./tracing/) | Sending an agent's traces to MLflow or any OTLP backend |

Each example works on the **Agents** page of the prokube UI or with `kubectl`.
The `kubectl` steps run from a prokube Lab terminal; from another terminal, add
`-n <workspace>` to each command.

## How agents are built

- **AgentTemplate**: what the agent does: model, instructions and tools.
- **Harness**: what it runs on. `default` is the kagent runtime; Claude Code,
  Codex and your own images are other harnesses.
- **EgressPolicy**: the hosts the agent may reach and the credentials the
  platform adds for them. Without one, an agent reaches only its model and
  tools.
- **SandboxTemplate**: the environment the agent's code runs in.
- **Agent**: one template on one harness, with its egress policies. Every
  conversation runs in its own isolated sandbox.
- **ModelConfig**: a model. Models an administrator grants through the AI
  Gateway appear in every workspace with origin **AI Gateway** and need no key.
