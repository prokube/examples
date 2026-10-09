# kagent examples

These examples introduce [kagent](https://kagent.dev/) one step at a time:

1. [`basic-agent`](./basic-agent/) deploys an agent without tools.
2. [`agent-with-mcp`](./agent-with-mcp/) gives an agent access to workspace MCP
   tools.
3. [`multi-agent`](./multi-agent/) delegates web research to another agent.
4. [`byo-langgraph-agent`](./byo-langgraph-agent/) runs a custom LangGraph
   workflow as a kagent BYO agent.

Complete the first three examples in order. The BYO example is standalone.

Each example has a notebook to run in a prokube Lab. Its README also covers the
same steps in a terminal and connecting from outside the cluster.

## Observability

[`observability/mlflow-tracing`](./observability/mlflow-tracing/) shows how to
send kagent traces from a workspace to an MLflow experiment.
