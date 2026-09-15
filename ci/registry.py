"""Example registration table. Add a new entry to EXAMPLES to include it in CI."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Step:
    """One execution unit within an Example — a notebook or a Python script."""

    kind: Literal["notebook", "script"]
    path: str  # relative to repo root
    extra_args: list[str] = field(default_factory=list)
    # True  → extract KFP run IDs from output (notebooks: broad UUID regex;
    #         scripts: KFP_RUN_ID=<uuid> lines).  Set False for ISVC examples
    #         whose output contains UUIDs that are not KFP run IDs.
    extract_run_ids: bool = True


@dataclass
class Example:
    """One CI example.  Add a new entry to EXAMPLES to include it in CI."""

    name: str
    steps: list[Step]
    phase: int  # 1 = independent  2 = pipeline submit  3 = needs mlflow model
    cleanup: str | None = None  # relative path to cleanup.py, or None
    opt_in: str | None = (
        None  # argparse dest that gates this example, e.g. "include_keda"
    )
    mlflow_dependent: bool = (
        False  # skip automatically when MLflow credentials are unavailable
    )
    api_key_dependent: bool = (
        False  # skip automatically when INFERENCE_SERVICE_API_KEY is unset
    )
    env_mutating: bool = False  # run first; modifies the shared Python environment


# ─────────────────────────────────────────────────────────────────────────────
# Registration table — add new examples here.
# ─────────────────────────────────────────────────────────────────────────────
EXAMPLES: list[Example] = [
    # ── Phase 1: independent, self-contained ─────────────────────────────────
    Example(
        name="notebooks/dask",
        steps=[Step("notebook", "notebooks/dask/dask_example.ipynb")],
        phase=1,
        cleanup="notebooks/dask/cleanup.py",
        env_mutating=True,
    ),
    Example(
        name="notebooks/mobile-price-classification",
        steps=[
            Step(
                "notebook",
                "notebooks/mobile-price-classification/mobile-price-classifications.ipynb",
            )
        ],
        phase=1,
    ),
    Example(
        name="mlflow/mlflow-quickstart",
        steps=[Step("notebook", "mlflow/mlflow-quickstart-example.ipynb")],
        phase=1,
        mlflow_dependent=True,
    ),
    Example(
        name="mlflow/mlflow-image-example",
        steps=[Step("notebook", "mlflow/mlflow-image-example.ipynb")],
        phase=1,
        mlflow_dependent=True,
    ),
    Example(
        name="mlflow/mlflow-kfp-example",
        steps=[Step("notebook", "mlflow/mlflow-kfp-example.ipynb")],
        phase=1,
        mlflow_dependent=True,
    ),
    Example(
        name="serving/minimal-s3-model",
        steps=[Step("notebook", "serving/minimal-s3-model/minimal-s3-model.ipynb")],
        phase=1,
        cleanup="serving/minimal-s3-model/cleanup.py",
        api_key_dependent=True,
    ),
    Example(
        name="serving/hf-vllm-completion",
        steps=[
            Step("script", "serving/hf-vllm-completion/apply.py", extract_run_ids=False)
        ],
        phase=1,
        cleanup="serving/hf-vllm-completion/cleanup.py",
    ),
    Example(
        name="serving/kserve-keda-autoscaling",
        steps=[
            Step(
                "script",
                "serving/kserve-keda-autoscaling/apply.py",
                extract_run_ids=False,
            )
        ],
        phase=1,
        opt_in="include_keda",
        cleanup="serving/kserve-keda-autoscaling/cleanup.py",
    ),
    Example(
        name="serving/minimal-example-shadow-deployment",
        steps=[
            Step(
                "script",
                "serving/minimal-example-shadow-deployment/apply.py",
                extract_run_ids=False,
            )
        ],
        phase=1,
        opt_in="include_shadow",
        cleanup="serving/minimal-example-shadow-deployment/cleanup.py",
    ),
    Example(
        name="notebooks/mnist-vae",
        steps=[
            Step(
                "script",
                "notebooks/mnist-vae/run_training.py",
                extra_args=["--max_epochs", "3"],
                extract_run_ids=False,
            ),
            Step(
                "notebook",
                "notebooks/mnist-vae/visualizations.ipynb",
                extract_run_ids=False,
            ),
        ],
        phase=1,
        opt_in="include_pytorch",
    ),
    # ── Phase 2: pipeline submissions (return fast; KFP runs polled in Phase 4)
    Example(
        name="mlflow/mobile-price-classification",
        steps=[
            Step(
                "notebook",
                "mlflow/mobile-price-classification/mlflow-mobile-price-classification.ipynb",
            )
        ],
        phase=2,
        mlflow_dependent=True,
    ),
    Example(
        name="pipelines/lightweight-components",
        steps=[
            Step(
                "notebook",
                "pipelines/lightweight-components/mobile-price-classifications.ipynb",
            )
        ],
        phase=2,
    ),
    Example(
        name="pipelines/lightweight-python-package",
        steps=[
            Step("script", "pipelines/lightweight-python-package/submit-cluster.py")
        ],
        phase=2,
    ),
    Example(
        name="pipelines/minimal-container-components",
        steps=[
            Step("script", "pipelines/minimal-container-components/submit-cluster.py")
        ],
        phase=2,
    ),
    # ── Phase 3: MLflow KServe ISVCs (need model registered by Phase 2) ──────
    Example(
        name="serving/mlflow-kserve-minimal",
        steps=[
            Step(
                "script",
                "serving/mlflow-kserve-minimal/apply.py",
                extract_run_ids=False,
            )
        ],
        phase=3,
        mlflow_dependent=True,
        api_key_dependent=True,
        cleanup="serving/mlflow-kserve-minimal/cleanup.py",
    ),
    Example(
        name="serving/mlflow-kserve-inference-protocols",
        steps=[
            Step(
                "script",
                "serving/mlflow-kserve-inference-protocols/apply.py",
                extract_run_ids=False,
            )
        ],
        phase=3,
        mlflow_dependent=True,
        api_key_dependent=True,
        cleanup="serving/mlflow-kserve-inference-protocols/cleanup.py",
    ),
]

# Cleanup scripts for resources not covered by an Example entry above. Only
# add a path here for a resource CI itself creates — hparam-tuning/minimal-mnist
# has no registered Example (it's a manual `kubectl apply` walkthrough), so its
# cleanup.py doesn't belong here: running it unconditionally on every CI run
# would delete a same-named Katib Experiment a user started manually in the
# shared namespace.
EXTRA_CLEANUP_PATHS: list[str] = []
