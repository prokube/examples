# Trace an agent in MLflow

This example sends what an agent does in each conversation, its model calls,
tool calls, timings and errors, to the workspace's MLflow.

## How it works

The workspace runs a small trace collector that forwards traces to MLflow,
to any OTLP endpoint such as Grafana Tempo or Langfuse, or to both. It signs in
with credentials from Secrets in the workspace; agents never see them. Nothing
is exported until you turn tracing on for an agent.

## Set up trace export

1. In MLflow, create an experiment and note its ID from the URL. Under
   **Permissions** > **Tokens**, create a token for a user with write access to
   the experiment.
2. Store the token in a Secret:

   ```bash
   kubectl create secret generic mlflow-tracing --from-literal=token=<your-token>
   ```

3. On the **Agents** page, open **Trace export** and select **Set up trace
   export**. Turn on **MLflow in this workspace** and enter the experiment ID,
   the MLflow user and the Secret. Add OTLP endpoints here as well if you use
   another backend.

## Try it

Create or edit an agent, for example `simple-assistant` from
[`basic-agent`](../basic-agent/), and turn on **Export traces**. Chat with it,
then open the experiment in MLflow and select **Traces**. Each answer is one
trace: `invoke_agent simple-assistant` with the model calls
(`generate_content`) and tool calls (`execute_tool`) below it.

Prompts and answers are recorded only if you turn on **Record prompts and
answers** in the trace export settings.

## Clean up

Turn off **Export traces** on the agent. To remove the collector, select
**Remove** under **Trace export**; traces already in MLflow stay.
