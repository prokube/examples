# Send agent traces to MLflow

This example sends the traces of a [kagent](https://kagent.dev/) agent to an
MLflow experiment. Tracing is off by default, and each agent opts in on its own.

## How it works

[`assistant.yaml`](./assistant.yaml) is the assistant from
[`basic-agent`](../../basic-agent/) with tracing enabled. It uses the Python
runtime and sends its traces to a collector in the workspace:

```yaml
spec:
  declarative:
    runtime: python
    deployment:
      env:
      - name: OTEL_TRACING_ENABLED
        value: "true"
      - name: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT
        value: http://otel-collector:4317
      - name: OTEL_EXPORTER_OTLP_TRACES_PROTOCOL
        value: grpc
      - name: OTEL_INSTRUMENTATION_A2A_SDK_ENABLED
        value: "false"
```

The last entry stops the A2A library, which receives the agent's messages,
from recording each of its internal steps as a span. Those spans make up
roughly half of a trace and show nothing about what the agent did.

[`otel-collector.yaml`](./otel-collector.yaml) deploys an
[OpenTelemetry Collector](https://opentelemetry.io/docs/collector/) that
forwards the traces to MLflow at `<MLFLOW_TRACKING_URI>/v1/traces`. It
authenticates with the `mlflow-credentials` Secret and selects the experiment
through its `MLFLOW_EXPERIMENT_ID` variable.

### Why the collector simplifies the trace

kagent records each message at several layers: the HTTP request, the agent
runner, the model client library, and every outgoing HTTP call. Each layer
adds its own spans, so a single message produces dozens of them, and the few
steps you care about are hard to find.

The collector keeps those steps and removes the rest before the trace reaches
MLflow. A trace then looks like this:

```text
invoke_agent tracing_assistant          the agent handling your message
└── chat claude-haiku-4-5-20251001      one model call: prompt, answer, tokens
    └── generate_content ...            tool calls the model requested
```

Each model call appears once with its token counts, so MLflow's token totals
stay correct. The comments in `otel-collector.yaml` explain each rule.

This view has limits:

- The agent span does not show your question and the final answer, because
  kagent 0.10 does not record them there. Open the `chat` span to see them.
- Tool calls appear below the model call that requested them, not next to it.
- The HTTP status of the request is removed together with the HTTP spans.
- If one agent calls another, the called agent's spans are no longer attached
  to that call. Use the diagnostic port below for such setups.

The rules match the span names of the kagent 0.10 Python runtime. If traces
look wrong after a kagent upgrade, compare them with a diagnostic trace and
adjust the rules.

### See every span

To troubleshoot an agent, point it at port 4319 instead:

```yaml
- name: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT
  value: http://otel-collector:4319
```

The collector forwards these traces to MLflow unchanged. Changing the endpoint
restarts the agent. Switch back to port 4317 when you are done.

The collector has no persistent queue. If it is unavailable, the agent keeps
answering, but the traces from that time are lost.

## Prerequisites

- The `anthropic-haiku` ModelConfig from [`basic-agent`](../../basic-agent/).
  To use another ModelConfig, change `modelConfig` in `assistant.yaml`.
- An MLflow server that accepts OTLP traces and authenticates with personal
  access tokens (PATs). The example is tested with MLflow 3.17.2 and
  mlflow-oidc-auth 11.0.2 including
  [prokube/mlflow-oidc-auth#11](https://github.com/prokube/mlflow-oidc-auth/pull/11).
- A kagent controller that leaves tracing to each agent instead of setting a
  global tracing endpoint, as in
  [prokube/prokube-neo#60](https://github.com/prokube/prokube-neo/pull/60).

Ask your platform admin if you are unsure whether your cluster meets these.

> [!WARNING]
> Traces contain prompts and answers, and everyone who can read the experiment
> can see them. Do not send sensitive data to a traced agent.

## Run the notebook

The easiest way to try the example is
[`mlflow-tracing.ipynb`](./mlflow-tracing.ipynb). Open it in a prokube Lab and
run its cells. It creates an experiment for you and waits until the trace
arrives in MLflow.

If you prefer a terminal, follow the steps below instead. They run from a
prokube Lab terminal in this directory and use its current workspace namespace.

## Create the credentials

Open **MLflow** in the prokube UI and create or select an experiment. Its ID is
the number after `experiments/` in the URL.

Create a PAT at `https://<your-prokube-domain>/mlflow/oidc/ui/auth`. The account
needs **EDIT** permission on the experiment. Everyone who can read Secrets in
the workspace can use these credentials, so in a shared workspace ask your admin
for a dedicated MLflow service account instead of using your own.

Create the `mlflow-credentials` Secret with the helper. It prompts for the
MLflow URL, your username, and the PAT:

```bash
python ../../../src/pk_helpers/mlflow_credentials.py
```

If the Secret already exists, for example from the [MLflow
examples](../../../mlflow/), the helper keeps it. Add `--rerun` to replace it.

You can create the same Secret under **K8s Secrets** in the prokube user menu
instead. Use `mlflow-credentials` as its name and `MLFLOW_TRACKING_URI`,
`MLFLOW_TRACKING_USERNAME`, and `MLFLOW_TRACKING_PASSWORD` as the keys.

## Deploy

Set your experiment ID in `otel-collector.yaml`:

```yaml
- name: MLFLOW_EXPERIMENT_ID
  value: "<experiment-id>"
```

Deploy the collector. If the workspace already runs an `otel-collector`, reuse
it instead of overwriting it.

```bash
kubectl apply -f otel-collector.yaml
kubectl rollout status deployment/otel-collector --timeout=2m
```

The collector reads its configuration only at startup. If you change it later,
apply the file again and run
`kubectl rollout restart deployment/otel-collector`.

Create the agent:

```bash
kubectl apply -f assistant.yaml
kubectl wait --for=condition=Ready \
  agents.kagent.dev/tracing-assistant --timeout=3m
```

## Verify

After the agent reaches `Ready`, open the [Agents page](/pkui/kagent) in the
prokube UI (`https://<your-prokube-domain>/pkui/kagent`), select
`tracing-assistant`, and send a message. Then open your experiment in MLflow.
The newest trace starts with the `invoke_agent tracing_assistant` span and
contains a `chat` span for the model call.

If no trace appears, check the collector logs:

```bash
kubectl logs deployment/otel-collector
```

Common causes are a wrong MLflow URL or experiment ID, or an account without
EDIT permission on the experiment.

## Enable tracing for an existing agent

Add the four `OTEL_*` entries from [`assistant.yaml`](./assistant.yaml) under
`spec.declarative.deployment.env` of the agent and keep its other entries. Edit
the Agent itself, for example with `kubectl edit agents.kagent.dev/<agent>` or
the YAML editor on the [Agents page](/pkui/kagent), not the Deployment that
kagent generates from it. Tracing requires `runtime: python`.

To turn tracing off again, remove the entries or set `OTEL_TRACING_ENABLED` to
`"false"`.

## Clean up

Delete the agent and the collector:

```bash
kubectl delete -f assistant.yaml
kubectl delete -f otel-collector.yaml
```

Turn off tracing for other agents that use the collector before you delete it.

Other MLflow examples use the `mlflow-credentials` Secret. If you do not need
it anymore, delete it and revoke the PAT in MLflow:

```bash
kubectl delete secret mlflow-credentials
```

The traces stay in the MLflow experiment.

## Production use

The collector is a starting point, not a production setup. See the
OpenTelemetry documentation on
[configuration](https://opentelemetry.io/docs/collector/configuration/),
[security and redaction](https://opentelemetry.io/docs/security/),
[sampling](https://opentelemetry.io/docs/concepts/sampling/), and
[resiliency](https://opentelemetry.io/docs/collector/resiliency/).
