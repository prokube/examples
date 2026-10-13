# kagent examples

These examples introduce [kagent](https://kagent.dev/) one step at a time:

1. [`basic-agent`](./basic-agent/) deploys an agent without tools.
2. [`agent-with-mcp`](./agent-with-mcp/) gives an agent access to workspace MCP
   tools.
3. [`multi-agent`](./multi-agent/) delegates web research to another agent.
4. [`byo-langgraph-agent`](./byo-langgraph-agent/) runs a custom LangGraph
   workflow as a kagent BYO agent.

Running the first three examples in order is recommended for a better
understanding, because each builds on the one before. Each notebook still runs
on its own and creates whatever the earlier examples would have; the terminal
steps in the READMEs expect the earlier examples' resources. The BYO example is
standalone.

Each example has a notebook to run in a prokube Lab. Its README also covers the
same steps in a terminal and connecting from outside the cluster.

## Terms

- **Agent**: a kagent resource that runs an LLM-based agent in your workspace.
  A *declarative* agent is defined entirely in YAML. A *BYO* (bring your own)
  agent runs your own container image. See
  [Agents](https://prokube.ai/docs/1.9/agentops/agents.html).
- **ModelConfig**: the model, provider, and credentials that declarative agents
  reference by name.
- **MCP**: the [Model Context Protocol](https://modelcontextprotocol.io/), which
  agents use to call tools. prokube publishes the workspace's MCP servers to
  kagent through the `gateway-mcp` `RemoteMCPServer`. See
  [MCP Federation and Tool Selection](https://prokube.ai/docs/1.9/agentops/agent_gateway.html#mcp-federation-and-tool-selection).
- **A2A**: the Agent2Agent protocol that clients and other agents use to send
  messages to an agent. An agent's **Agent Card** describes its name,
  capabilities, and endpoint to A2A clients.
- **Agent Gateway**: routes model, tool, and agent traffic. Workloads in the
  workspace, such as a Lab, call agents through internal routes without an API
  key. External clients use `/svc/a2a/<workspace>/<agent>` with an API key. See
  [Public vs. Internal Traffic](https://prokube.ai/docs/1.9/platform/agent_gateway.html#public-vs-internal-traffic).
- **Lab**: a notebook environment, such as JupyterLab, that runs in your
  workspace. See [Labs](https://prokube.ai/docs/1.9/labs/index.html).
