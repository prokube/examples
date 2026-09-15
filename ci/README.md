# CI contributor guide

This guide explains how contributors and automation agents can run the example
suite and register new examples in the `ci` package (`python -m ci`).

---

## Running CI

Run the suite from a Kubeflow notebook pod with this repository checked out:

```bash
python -m pip install -e ".[ci]"
python -m ci
```

To preview the execution plan without running any examples:

```bash
python -m ci --dry-run
```

MLflow examples require the `mlflow-credentials` Kubernetes secret. Serving
examples that use external authentication require
`INFERENCE_SERVICE_API_KEY`. Examples with unavailable prerequisites are
reported as skipped. Run `python -m ci --help` for timeout and opt-in
options.

If the notebook was created by hand (not via the JupyterLab UI), it needs the
prokube PodDefault labels `access-ml-pipeline=true` and
`add-minio-service-account-token=true` — without them the s3 and KFP examples
fail instantly with missing `AWS_*` / `KF_PIPELINES_SA_TOKEN`.

---

## Adding a new example

Register it in the `EXAMPLES` list in `ci/registry.py`. Phase scheduling,
cleanup, dry-run output, credential checks, and environment-mutating ordering
are derived from this entry. Opt-in examples require the additional changes
described below.

Package layout:

| Module | Contents |
|--------|----------|
| `ci/registry.py` | `Step`, `Example`, and the `EXAMPLES` registration table |
| `ci/runner.py` | Phase orchestration and `run_all()` |
| `ci/__main__.py` | CLI flags (`python -m ci`) |
| `ci/preflight.py` | Dependency, MLflow credential, and API key checks |
| `ci/notebook.py` | Papermill execution and KFP run-ID extraction |
| `ci/process.py` | Cancellable subprocess and cleanup.py runners |
| `ci/kfp_runs.py` | KFP run polling and failed-task log tailing |
| `ci/results.py` | `Result` record, final report, dry-run listing |

```python
Example(
    name="serving/my-new-example",       # display name and result key
    steps=[
        Step("script", "serving/my-new-example/apply.py"),
        # or: Step("notebook", "serving/my-new-example/example.ipynb")
        # chain multiple steps if needed (executed sequentially)
    ],
    phase=1,                             # see Phase rules below
    cleanup="serving/my-new-example/cleanup.py",  # omit if no Kubernetes resources
    opt_in="include_foo",                # omit if always enabled
    mlflow_dependent=False,              # True = skip when MLflow creds absent
    api_key_dependent=False,             # True = skip when INFERENCE_SERVICE_API_KEY is unset
    env_mutating=False,                  # True = pip installs/upgrades packages;
                                          # runs before the rest of its phase (see below)
)
```

### env_mutating flag

Papermill executes each notebook in a separate `python3` kernel process, but
all kernels use the same Python environment and site-packages. CI does not
create an isolated environment for each notebook. If one notebook runs
`pip install --upgrade <pkg>` while another notebook is importing that
package, the concurrent reinstall can corrupt the import (e.g. `ModuleNotFoundError:
No module named 'pandas._libs.internals'` from a partially-replaced
compiled extension).

Set `env_mutating=True` when an example runs an active `pip install` or
`%pip install` command that installs or upgrades packages imported by other
examples in the same phase. Ignore commented-out installation examples.
`ci/runner.py` runs all `env_mutating` examples in a
phase to completion **before** starting the rest of that phase, instead of
placing everything in the same parallel batch. Prefer avoiding
`pip install --upgrade` in new examples entirely (pin/bake deps into the
notebook image); use `env_mutating=True` only when that is not
possible.

### Phase rules

| Phase | When to use |
|-------|-------------|
| 1 | Self-contained: does not depend on anything else in CI |
| 2 | Submits a KFP pipeline and returns fast; actual run is polled in Phase 4 |
| 3 | Requires a model already registered by the Phase 2 mlflow-mobile-price pipeline |

### Opt-in flag

Use opt-in when an example requires cluster add-ons (KEDA,
`postgres-operator`, GPU nodes) that may not be present. Add
`opt_in="include_foo"` to the `Example`, add an `include_foo` parameter to
`run_all()` in `ci/runner.py`, include it in the `opts` mapping, define the
`--include-foo` argument in `ci/__main__.py`, and pass the parsed value to
`run_all()`.

`--include-shadow` also needs the notebook ServiceAccount to manage
`postgresclusters.postgres-operator.crunchydata.com`, which it can't out of
the box. Patching `ClusterRole/kubeflow-kubernetes-edit` is reverted by
ArgoCD within minutes; a namespaced `Role`/`RoleBinding` on `default-editor`
in the workspace holds instead.

---

## apply.py and cleanup.py

### cleanup.py — always add when Kubernetes resources are created

Any example that creates Kubernetes resources (InferenceService, Deployment,
Service, CRD instance, …) must have a `cleanup.py` in its directory.
CI runs all cleanup scripts in parallel in a `finally` block so they execute
even on failure. This is best-effort: `_run_cleanup` gives each script a
120s budget and does not fail CI on a non-zero exit or timeout (only a
warning is logged) — cleanup failures are not treated as example failures.

A cleanup script must:
- Delete resources idempotently (`--ignore-not-found`)
- Never raise on failure (print a warning at most)
- Read the namespace from the pod filesystem:

```python
with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace") as f:
    ns = f.read().strip()
```

**Do not** add a `cleanup.py` for examples that only create in-cluster
transient objects managed by KFP (pipeline runs, artifacts) — those are
cleaned up by KFP's own retention policy.

### apply.py — only for serving examples driven by a script

Add an `apply.py` only when the CI execution of a serving example is driven
by a Python script rather than a notebook.  This is the case when:

- The notebook's deploy/test section requires manual inputs that cannot be
  automated, so a separate script owns the full deploy-wait-smoketest cycle.
- The example has no notebook at all.

An `apply.py` must exit non-zero on failure (CI relies on the return code).
It must print a clean error message to stderr and suppress the full traceback:

```python
if __name__ == "__main__":
    try:
        deploy()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
```

If you add an `apply.py`, always add the matching `cleanup.py` as well.

---

## pk_helpers

`pk_helpers` (source in `src/pk_helpers/`) contains prokube platform utilities
for notebooks and apply scripts. Notebooks load only the required script using
a path relative to the notebook directory, so users do not need to install the
package (this example assumes a notebook one directory below the repository root):

```python
%run -n ../src/pk_helpers/mlflow_credentials.py
```

The `-n` option loads the functions without running the script's command-line
entry point. Interactive cells can then call the required function directly.

CI installs the package during preflight. Standalone `apply.py` scripts install
it automatically if it is not already available, so those scripts can use
normal package imports.

To install the package manually in an activated virtual environment, run:

```bash
python -m pip install -e .
```

### setup_mlflow_credentials

Interactive. Stores MLflow credentials in the `mlflow-credentials` Kubernetes
Secret. First, create a Personal Access Token from `/mlflow/oidc/ui/auth` on
your prokube domain. Then run the setup cell; the script prompts for the MLflow
URI, email address, and token, and creates the Secret:

```python
# Creates the Secret if it doesn't exist.
setup_mlflow_credentials()

# To recreate the secret with new credentials, run:
# setup_mlflow_credentials(rerun=True)
```

If the secret exists, the cell skips setup. Use
`setup_mlflow_credentials(rerun=True)` to replace it. Tag this interactive cell
with `ci-skip`. CI removes it before execution and validates the preconfigured
secret during preflight.

### load_mlflow_credentials

Call this from a notebook that communicates with MLflow directly rather than
through a KFP pipeline. It first uses `MLFLOW_TRACKING_URI`,
`MLFLOW_TRACKING_USERNAME`, and `MLFLOW_TRACKING_PASSWORD` if all three are
set. Otherwise, it reads the `mlflow-credentials` Kubernetes secret. It adds
the resolved values and `MLFLOW_ENABLE_PROXY_MULTIPART_UPLOAD=true` to
`os.environ`, and raises a clear `RuntimeError` if no credentials are
available.

```python
%run -n ../src/pk_helpers/mlflow_credentials.py
load_mlflow_credentials()
```

### require_mlflow_secret

Call this before building or submitting a KFP pipeline whose tasks read MLflow
credentials via `use_secret_as_env(secret_name="mlflow-credentials", ...)`.
It checks that the secret exists before the pipeline is submitted, so a
missing secret produces a clear error in the notebook. Pipeline components
run in separate pods and must read credentials from the Kubernetes secret;
variables set only in the notebook are not available to them.

```python
%run -n ../src/pk_helpers/mlflow_credentials.py
require_mlflow_secret()
```

### get_or_create_api_key

Returns a model-serving API key: the `INFERENCE_SERVICE_API_KEY` env var if
an admin has injected one into the pod, otherwise an interactive prompt
(ask your cluster admin, or use pkui if available on your platform). Call it
from any notebook cell or script that needs an inference API key:

```python
%run -n ../src/pk_helpers/api_key.py
API_KEY = get_or_create_api_key()
```

CI runs headlessly and cannot answer the interactive prompt, so
`INFERENCE_SERVICE_API_KEY` **must** be exported before running
`python -m ci`:

```bash
export INFERENCE_SERVICE_API_KEY=<your-api-key>   # ask your admin, or use pkui if available
```

CI validates this in the preflight check and skips `api_key_dependent`
examples if it is unset — mark any new example that calls
`get_or_create_api_key()` with `api_key_dependent=True`.

Agent Gateway serving routes require `aiGateway.controller.enabled=true`.

### internal_predict_url / external_predict_url

The helpers detect the cluster generation by checking whether the
`agentgateway-proxy` Service resolves through cluster DNS. Legacy clusters use
the predictor Service internally and the InferenceService's `.status.url`
externally. Clusters with Agent Gateway use its internal and external routes;
these clusters are expected to have `aiGateway.controller.enabled=true`.

- `internal_predict_url(isvc_name, namespace, model_name)` returns the
  **internal, in-cluster** predict URL. Agent Gateway clusters use
  `http://agentgateway-proxy.agentgateway-system.svc.cluster.local/_platform/serving/<namespace>/<isvc-name>/...`;
  legacy clusters use `http://<isvc-name>-predictor.<namespace>.svc.cluster.local/...`.
- `external_predict_url(isvc_url, model_name, protocol="v1")` returns one
  **external** predict URL from an ISVC's `.status.url`. Agent Gateway clusters
  use `https://<domain>/svc/serving/<namespace>/<isvc-name>/...`; legacy
  clusters use the unmodified `/serving` path from `.status.url`.

```python
%run -n ../src/pk_helpers/kserve_url.py
internal_url = internal_predict_url(isvc_name, namespace, model_name)
external_url = external_predict_url(isvc_status_url, model_name)
```

---

## ci-skip cell tag

Tag a notebook cell with `ci-skip` to have CI replace it with a no-op comment
before execution.  Use this **only** for cells that genuinely cannot run
headlessly:

- Cells that require manual input (hardcoded paths, paste-your-token
  placeholders, `input()` calls).
- Interactive widget cells (`ipywidgets`, `ipykernel` display-only code).

**Do not** use `ci-skip` to work around a fixable automation problem.  If a
cell fails because it needs credentials or a namespace, fix it to load those
automatically (see the MLflow credential pattern above).  `ci-skip` is a last
resort, not a convenience.

To tag a cell in JupyterLab: select the cell → Property Inspector (right
panel) → add `ci-skip` under Cell Tags.

In raw notebook JSON the tag appears as:

```json
"metadata": {
    "tags": ["ci-skip"]
}
```
