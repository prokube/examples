# Send kagent traces to MLflow

This example shows how to use the
[OpenTelemetry Collector](https://opentelemetry.io/docs/collector/) to send
kagent traces to [MLflow](https://mlflow.org/). Other OpenTelemetry-compatible
observability backends, such as [Langfuse](https://langfuse.com/), can be used
in a similar way by configuring the corresponding exporter and credentials.

Run the commands below from this directory. Set your workspace namespace once:

```bash
export NAMESPACE=<workspace>
```

## Prerequisites

- The cluster runs the prokube MLflow 3.16 integration.
- An administrator has enabled kagent workspace tracing and registered your
  workspace with the central trace router.
- A kagent agent is ready in the workspace. Start with the
  [basic agent example](../../basic-agent/) if needed.

## Create an experiment and access token

Open **MLflow** in the prokube UI, create an experiment, and open it. Its URL
contains the numeric experiment ID after `experiments/`; keep this ID for the
next step.

Open **Permissions** in MLflow, select **Create access key**, and copy the new
personal access token. MLflow shows the token only once.

> [!WARNING]
> Workspace contributors can read Secrets in their namespace. A personal token
> is suitable for a personal quickstart. For a shared workspace, ask an
> administrator for a restricted MLflow service account instead.

## Create the credentials Secret

Create the Secret in the workspace:

```bash
kubectl create secret generic mlflow-credentials \
  -n "$NAMESPACE" \
  --from-literal=MLFLOW_TRACKING_URI='https://<your-prokube-domain>/mlflow' \
  --from-literal=MLFLOW_TRACKING_USERNAME='<your-email>' \
  --from-literal=MLFLOW_TRACKING_PASSWORD='<your-access-token>' \
  --from-literal=MLFLOW_EXPERIMENT_ID='<numeric-experiment-id>'
```

Use the MLflow base URL ending in `/mlflow`, not the `/v1/traces` ingestion
path. The collector adds that path automatically.

## Deploy the collector

```bash
kubectl apply -n "$NAMESPACE" -f otel-collector.yaml
kubectl rollout status -n "$NAMESPACE" deployment/otel-collector --timeout=2m
kubectl get -n "$NAMESPACE" service otel-collector
```

The Service must remain named `otel-collector`. kagent agents send their spans
to this namespace-local name, while the platform trace router sends the
controller spans for the same trace to it.

## View a trace

Open **Agents** in the prokube UI, select an agent in this workspace, and send a
chat message. Then open the MLflow experiment and select its newest trace. A
complete trace includes the controller request and the agent invocation spans.

## Use with GitOps

Commit `otel-collector.yaml` to the repository that manages your workspace and
deploy it through your existing GitOps process. Store `mlflow-credentials`
through your organization's secret-management mechanism; do not commit the
token to Git.

## Clean up

```bash
kubectl delete -n "$NAMESPACE" -f otel-collector.yaml
```

This removes the collector but does not delete the credentials Secret, the
MLflow experiment, or its existing traces. If you created `mlflow-credentials`
only for this quickstart, delete it separately. Revoke the personal access
token in MLflow if it is no longer needed.

## Customize the collector

This example intentionally uses one small collector without advanced sampling,
redaction, scaling, or production hardening. For those topics, use the upstream
OpenTelemetry documentation:

- [Collector configuration](https://opentelemetry.io/docs/collector/configuration/)
- [Processors](https://opentelemetry.io/docs/collector/components/processor/)
- [Sampling](https://opentelemetry.io/docs/concepts/sampling/)
- [Security guidance](https://opentelemetry.io/docs/security/)
- [Collector deployment](https://opentelemetry.io/docs/collector/deploy/)
