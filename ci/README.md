# CI — contributor guide

> This document is written primarily for AI agents making changes to this
> repository.  It describes the conventions that must be followed for a new
> example to be picked up by `ci/run_all.py` correctly.

---

## Adding a new example

Register it in the `_EXAMPLES` list in `run_all.py`.  Everything else —
phase scheduling, opt-in gating, cleanup, dry-run output, MLflow-credential
skipping — is derived from that entry automatically.

```python
Example(
    name="serving/my-new-example",       # display name and result key
    steps=[
        Step("script", "serving/my-new-example/apply.py"),
        # or: Step("notebook", "serving/my-new-example/example.ipynb")
        # chain multiple steps if needed (executed sequentially)
    ],
    phase=1,                             # see Phase rules below
    cleanup="serving/my-new-example/cleanup.py",  # omit if no K8s resources
    opt_in="include_foo",                # omit if always enabled
    mlflow_dependent=False,              # True = skip when MLflow creds absent
)
```

### Phase rules

| Phase | When to use |
|-------|-------------|
| 1 | Self-contained: does not depend on anything else in CI |
| 2 | Submits a KFP pipeline and returns fast; actual run is polled in Phase 4 |
| 3 | Requires a model already registered by the Phase 2 mlflow-mobile-price pipeline |

### Opt-in flag

Add `opt_in="include_foo"` and a corresponding `--include-foo` argument in
the `__main__` block of `run_all.py`.  Use opt-in when the example requires
cluster add-ons (KEDA, postgres-operator, GPU nodes) that are not guaranteed
to be present.

---

## apply.py and cleanup.py

### cleanup.py — always add when K8s resources are created

Any example that creates Kubernetes resources (InferenceService, Deployment,
Service, CRD instance, …) must have a `cleanup.py` in its directory.
CI runs all cleanup scripts in parallel in a `finally` block so they execute
even on failure.

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

## scripts/ utilities

`scripts/` contains two cluster utilities importable from notebooks and apply
scripts.  Both work identically whether called from a notebook cell or from an
`apply.py`.

### setup_mlflow_credentials.py

One-time, interactive.  Stores MLflow credentials in the
`mlflow-credentials` K8s secret.  **Requires human input** (the MLflow
Personal Access Token cannot be obtained programmatically).  Run it once from
a JupyterLab terminal:

```bash
python examples/scripts/setup_mlflow_credentials.py
```

Do not call this from CI.  CI validates the secret exists in the preflight
check and skips MLflow-dependent examples if it does not.

### get_or_create_api_key.py

Returns a model-serving API key: the `INFERENCE_SERVICE_API_KEY` env var if
an admin has injected one into the pod, otherwise an interactive prompt
(ask your cluster admin, or use pkui if available on your platform). Call it
from any notebook cell or script that needs an inference API key:

```python
import sys, subprocess, os
_root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
sys.path.insert(0, os.path.join(_root, "scripts"))
from get_or_create_api_key import get_or_create_api_key

API_KEY = get_or_create_api_key()
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
