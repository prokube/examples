# Send kagent traces to MLflow

Opt in one Python Agent and deploy one small workspace-local
[OpenTelemetry Collector](https://opentelemetry.io/docs/collector/):

```text
Python Agent -> otel-collector:4317 (OTLP/gRPC)
             -> https://<your-prokube-domain>/mlflow/v1/traces (OTLP/HTTP)
```

Tracing is optional and off by default. This example does not provision a
global collector or register workspaces with a router. Export is best effort:
Agent requests can continue when the collector is unavailable, but traces can
be lost during outages. The collector has no persistent queue.

## Prerequisites

- An existing prokube workspace with kagent enabled and a working, user-selected
  ModelConfig in that namespace. The [basic agent example](../../basic-agent/)
  uses `anthropic-haiku`; reuse it or choose an existing ModelConfig for your
  provider. This quickstart creates no provider keys.
- The **revised, neutral controller environment** from
  [prokube/prokube-neo PR60](https://github.com/prokube/prokube-neo/pull/60):
  controller tracing stays disabled and does not inject a global tracing
  endpoint/protocol into Agents. Each Agent owns its explicit opt-in settings.
  Ask your administrator to confirm the deployed configuration, not just the
  PR number; the earlier globally enabled PR60 configuration is not sufficient.
- A compatible MLflow server with OTLP ingestion, Basic authentication using
  personal access tokens (PATs), and a **SQL-backed store**. The validated
  combination is **MLflow 3.17.2 + mlflow-oidc-auth 11.0.2**, with the changes
  from [prokube/mlflow-oidc-auth PR11](https://github.com/prokube/mlflow-oidc-auth/pull/11).
  This is a prerequisite, not a claim that this image is installed on every
  prokube cluster. The closed PR9 and prokube PR401 are superseded, not working
  prerequisites. No MLflow server is installed by this example.
- Existing workspace mesh identity and network policies must allow the Agent
  to reach the collector and the collector to reach authenticated MLflow.
  Keep normal Istio HTTP probe rewriting enabled. Do not add anonymous health
  or authentication-policy bypasses.

Run terminal commands from this directory, using your existing namespace:

```bash
export NAMESPACE=<workspace>
```

## 1. Choose an experiment and credentials

Open **MLflow** in the prokube UI and create or select an experiment. Its URL
contains the numeric experiment ID after `experiments/`.

For a shared workspace, ask an administrator for a **workspace MLflow service
account** with **EDIT** permission on that experiment and a PAT for that account.
This is an MLflow identity, not a Kubernetes ServiceAccount. For a personal
quickstart, your own account and PAT can be used if it has EDIT permission.
Open the MLflow user's access-token management page and create a named PAT with
an expiry. Store its secret securely; it is shown only at creation.

> [!WARNING]
> Traces can contain prompts, completions, and other sensitive context. Opting
> in sends that data to the MLflow URL and experiment you select below, where
> experiment readers can access it. Use a non-sensitive test message. Workspace
> contributors who can read Secrets can also use the collector's credentials.
> Do not print credentials, paste them into chat, or commit them to Git.

## 2. Create the credentials Secret

Under **K8s Secrets** in the prokube user menu, create `mlflow-credentials` in
your workspace with these keys, or reuse a Secret with exactly this contract:

| Key | Value |
|---|---|
| `MLFLOW_TRACKING_URI` | `https://<your-prokube-domain>/mlflow` |
| `MLFLOW_TRACKING_USERNAME` | The MLflow account's username |
| `MLFLOW_TRACKING_PASSWORD` | That account's PAT, not its login password |
| `MLFLOW_EXPERIMENT_ID` | The numeric experiment ID as a string |

Use the base URL ending in `/mlflow`, without a trailing slash or `/v1/traces`.
The collector appends `/v1/traces`, authenticates with Basic username/PAT, and
sets `X-Mlflow-Experiment-Id` from this Secret. Do not put credentials in the
Agent, ConfigMap, command history, or checked-in manifests.

For a terminal alternative, use an interactive shell so the PAT is not stored
in command history or passed as a command-line argument:

```bash
read -r -p 'MLflow base URL: ' MLFLOW_TRACKING_URI
read -r -p 'MLflow username: ' MLFLOW_TRACKING_USERNAME
read -r -p 'Experiment ID: ' MLFLOW_EXPERIMENT_ID
read -r -s -p 'MLflow PAT: ' MLFLOW_TRACKING_PASSWORD
printf '\n'
{
  printf 'MLFLOW_TRACKING_URI=%s\n' "$MLFLOW_TRACKING_URI"
  printf 'MLFLOW_TRACKING_USERNAME=%s\n' "$MLFLOW_TRACKING_USERNAME"
  printf 'MLFLOW_TRACKING_PASSWORD=%s\n' "$MLFLOW_TRACKING_PASSWORD"
  printf 'MLFLOW_EXPERIMENT_ID=%s\n' "$MLFLOW_EXPERIMENT_ID"
} | kubectl create secret generic mlflow-credentials -n "$NAMESPACE" \
    --from-env-file=/dev/stdin
unset MLFLOW_TRACKING_PASSWORD
```

## 3. Deploy the collector and opt in the Agent

Deploy the collector first:

If the workspace already has a collector named `otel-collector`, ask its owner
whether to reuse it. Do not apply this example over a collector managed by
another user or platform component.

```bash
kubectl apply -n "$NAMESPACE" -f otel-collector.yaml
kubectl rollout status -n "$NAMESPACE" deployment/otel-collector --timeout=2m
```

[`otel-collector.yaml`](./otel-collector.yaml) contains only a ConfigMap,
Deployment, and Service. It pins contrib `0.159.0`, runs non-root with small
resource limits, and receives OTLP/gRPC on the workspace-local Service
`otel-collector:4317`. Its HTTP probes use normal mesh probe rewriting; no
AuthorizationPolicy is added or relaxed.

For a **new Agent**, open **Agents** in the prokube UI and use YAML create.
Paste the full root from [`assistant.yaml`](./assistant.yaml). Keep the new
name `tracing-assistant`, and set `spec.declarative.modelConfig` to your
**existing** ModelConfig (`anthropic-haiku` only if you already created it).
The manifest explicitly selects `runtime: python` and `a2aConfig: {}`.

Alternatively, edit that same file locally and apply it:

```bash
kubectl apply -n "$NAMESPACE" -f assistant.yaml
kubectl wait -n "$NAMESPACE" --for=condition=Ready \
  agents.kagent.dev/tracing-assistant --timeout=3m
```

For an **existing Python Agent**, use YAML edit on its full Agent root. Under
`spec.declarative.deployment.env`, add or update these three entries by name:

```yaml
- name: OTEL_TRACING_ENABLED
  value: "true"
- name: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT
  value: http://otel-collector:4317
- name: OTEL_EXPORTER_OTLP_TRACES_PROTOCOL
  value: grpc
```

Preserve every other env entry, `envFrom`, resource setting, volume, and other
deployment field. Do not apply the new-Agent sample over an existing Agent or
use a JSON merge patch that replaces the env array. Keep its existing model,
instructions, tools, and A2A settings. This path is for the Python runtime;
switching an existing Go Agent to Python is a separate compatibility decision.
Save the Agent root, not the generated Deployment. pkui must preserve these
fields on later edits; if your installed form editor does not, keep using the
full YAML root rather than a form save that drops them.

## 4. Chat and verify

After the Agent reaches `Ready`, select it on **Agents** in the prokube UI and
send a non-sensitive message. Open the selected MLflow experiment and inspect
the newest trace: confirm the message, AGENT and LLM spans, and a connected
parent/child tree. No controller span is required. This minimal Agent has no
tools, so it does not demonstrate tool spans.

If no trace appears, check Agent readiness, the three env values on its root,
the collector rollout, the Secret's URL/experiment, and the MLflow identity's
EDIT permission. Inspect collector errors without dumping the Secret or
sharing logs that contain sensitive data. Successful chat alone does not
prove export; an outage trace may be lost even after the collector recovers.

## GitOps and cleanup

Both the Agent root and collector manifests are user-managed Kubernetes
resources supported by your existing workspace GitOps process. Commit only
non-secret intent and use your organization's secret-management mechanism for
`mlflow-credentials`. No Helm release, operator, ArgoCD Application, or namespace
foundation is needed here. Do not manage the Agent's generated Deployment.

For the new sample Agent, clean up with:

```bash
kubectl delete -n "$NAMESPACE" -f assistant.yaml
kubectl delete -n "$NAMESPACE" -f otel-collector.yaml
```

For an existing Agent, instead remove only the tracing entries you added (or
set `OTEL_TRACING_ENABLED` to `"false"`), preserving the rest of its root. Do
this before removing a collector used by that Agent. With GitOps, remove the
corresponding intent from its source of truth instead of issuing deletes.
Do not delete a collector still used by other Agents.

Keep the existing ModelConfig and provider credentials. Delete
`mlflow-credentials` only if it was created solely for this quickstart, and
revoke the PAT if no longer needed. Cleanup does not delete the MLflow
experiment or its traces; manage their retention in MLflow.

## Validation scope and production topics

The recorded OVH platform spike used the versions above and a deterministic
OpenAI-compatible fixture, not a real model or tool. It produced two connected
56-span traces (one root, no broken parents), verified no exports from a
disabled Agent, and demonstrated a successful request with a lost trace while
the collector was absent, followed by restored export. That is integration
evidence for that environment, not a portable expected trace ID or validation
of a real provider, tool spans, the public gateway, or browser UI. This
quickstart still needs verification against your deployed prerequisites.

For local YAML semantics checks (no cluster or credentials required):

```bash
uv run --no-project --with pytest --with pyyaml pytest -q test_manifests.py
```

This is an initial configuration, not a production telemetry design. Use the
upstream guidance for [Collector configuration](https://opentelemetry.io/docs/collector/configuration/),
[security and redaction](https://opentelemetry.io/docs/security/),
[sampling](https://opentelemetry.io/docs/concepts/sampling/), and
[queues, retries, and persistence](https://opentelemetry.io/docs/collector/resiliency/).
