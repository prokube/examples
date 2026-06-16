"""
CI orchestrator — runs all automatable examples and reports results.

Execution model
---------------
Phase 1 (parallel, self-contained):
    All examples whose phase=1 in _EXAMPLES, including opt-in ones.

Phase 2 (parallel, pipeline submissions — return fast):
    All examples whose phase=2 in _EXAMPLES.

Phase 3 (depends on Phase 2 mlflow-mobile-price notebook completing):
    All examples whose phase=3 in _EXAMPLES.

Phase 4 (KFP run polling — runs alongside Phase 3):
    Poll all KFP run IDs extracted from Phase 2 output notebooks until
    Succeeded or timeout.

Phase 5 — cleanup (always, in finally block):
    All cleanup.py scripts derived from _EXAMPLES, in parallel.

Adding a new example
--------------------
Add one entry to _EXAMPLES below. Everything else (cleanup, phase
scheduling, opt-in gating, dry-run output) is derived from the table.

Usage from a Jupyter notebook
------------------------------
    import subprocess
    subprocess.run(["python", "ci/run_all.py"], check=True)

CLI usage
---------
    python ci/run_all.py [--timeout-notebook 1800] [--timeout-pipeline 3600]
                         [--include-keda] [--include-shadow] [--include-pytorch]
                         [--dry-run]

Prerequisites
-------------
    pip install papermill kfp
    python scripts/setup_mlflow_credentials.py
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal


# ── Repo root ─────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(
    subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
)


# ── Prerequisite: papermill ───────────────────────────────────────────────────


def _ensure_papermill() -> None:
    """Install papermill if it is not already available."""
    try:
        import papermill  # noqa: F401
    except ImportError:
        print("papermill not found — installing...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "papermill"],
            check=True,
        )
        print("papermill installed.")


# ── KFP run ID pattern (UUID v4) ─────────────────────────────────────────────
_RUN_ID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


# ── Result dataclass ──────────────────────────────────────────────────────────


@dataclass
class Result:
    name: str
    status: str = "PENDING"  # PASS | FAIL | SKIP
    duration: float = 0.0
    error: str = ""
    kfp_run_ids: list[str] = field(default_factory=list)


# ── Example registry ──────────────────────────────────────────────────────────


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
    """One CI example.  Add a new entry to _EXAMPLES to include it in CI."""

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


# ─────────────────────────────────────────────────────────────────────────────
# Registration table — add new examples here.
# ─────────────────────────────────────────────────────────────────────────────
_EXAMPLES: list[Example] = [
    # ── Phase 1: independent, self-contained ─────────────────────────────────
    Example(
        name="notebooks/dask",
        steps=[Step("notebook", "notebooks/dask/dask_example.ipynb")],
        phase=1,
        cleanup="notebooks/dask/cleanup.py",
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
        cleanup="serving/mlflow-kserve-inference-protocols/cleanup.py",
    ),
]

# Cleanup scripts for resources not covered by an Example entry above.
_EXTRA_CLEANUP_PATHS: list[str] = [
    "hparam-tuning/minimal-mnist/cleanup.py",
]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _namespace() -> str:
    with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace") as fh:
        return fh.read().strip()


def _format_papermill_error(exc: Exception) -> str:
    """Extract a human-readable summary from a PapermillExecutionError."""
    try:
        from papermill.exceptions import PapermillExecutionError

        if not isinstance(exc, PapermillExecutionError):
            return str(exc)
    except ImportError:
        return str(exc)

    lines = [
        f"Cell {exc.exec_count} raised {exc.ename}: {exc.evalue}",
    ]
    if exc.source:
        src_lines = exc.source.strip().splitlines()[:5]
        lines.append("  Cell source:")
        for src_line in src_lines:
            lines.append(f"    {src_line}")
        if len(exc.source.strip().splitlines()) > 5:
            lines.append("    ...")
    if exc.traceback:
        tb_lines = [l for l in exc.traceback if l.strip()]
        if tb_lines:
            lines.append(f"  Traceback (last): {tb_lines[-1].strip()}")
    return "\n".join(lines)


def _strip_ci_skip_cells(nb_path: Path, output_dir: Path) -> Path:
    """Return a copy of the notebook with 'ci-skip' tagged cells replaced by a comment."""
    with open(nb_path) as fh:
        nb = json.load(fh)
    skipped = 0
    for cell in nb["cells"]:
        if "ci-skip" in cell.get("metadata", {}).get("tags", []):
            cell["source"] = ["# [CI] cell skipped (ci-skip tag)\n"]
            skipped += 1
    if skipped == 0:
        return nb_path
    stripped = output_dir / f"_stripped_{nb_path.name}"
    stripped.parent.mkdir(parents=True, exist_ok=True)
    with open(stripped, "w") as fh:
        json.dump(nb, fh, indent=1)
    print(f"  ({skipped} ci-skip cell(s) stripped from {nb_path.name})")
    return stripped


def _run_notebook(nb_path: Path, output_dir: Path, timeout: int) -> Path:
    """Execute a notebook with papermill. Returns the output notebook path."""
    import papermill as pm
    from papermill.exceptions import PapermillExecutionError

    output_dir.mkdir(parents=True, exist_ok=True)
    nb_to_run = _strip_ci_skip_cells(nb_path, output_dir)
    output_path = output_dir / nb_path.name
    try:
        pm.execute_notebook(
            str(nb_to_run),
            str(output_path),
            kernel_name="python3",
            execution_timeout=timeout,
            cwd=str(nb_path.parent),
            progress_bar=False,
        )
    except PapermillExecutionError as exc:
        raise RuntimeError(_format_papermill_error(exc)) from exc
    return output_path


def _run_script(
    script_path: Path,
    timeout: int,
    extra_args: list[str] | None = None,
) -> tuple[str, str]:
    """Run a plain Python script. Returns (stdout, stderr)."""
    cmd = [sys.executable, str(script_path)] + (extra_args or [])
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(script_path.parent),
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "(no output)").strip()
        raise RuntimeError(detail)
    return result.stdout, result.stderr


def _extract_run_ids_from_notebook(output_nb: Path) -> list[str]:
    """Parse a papermill output notebook for KFP run IDs."""
    with open(output_nb) as fh:
        nb = json.load(fh)
    ids: list[str] = []
    for cell in nb.get("cells", []):
        for output in cell.get("outputs", []):
            text = "".join(
                output.get("text", []) + output.get("data", {}).get("text/plain", [])
            )
            ids.extend(_RUN_ID_RE.findall(text))
    return list(dict.fromkeys(ids))


def _extract_run_ids_from_stdout(stdout: str) -> list[str]:
    """Parse stdout from a script for KFP_RUN_ID=<uuid> lines."""
    ids = []
    for line in stdout.splitlines():
        if line.startswith("KFP_RUN_ID="):
            ids.append(line.split("=", 1)[1].strip())
    return ids


_KFP_TERMINAL_STATES = {"SUCCEEDED", "FAILED", "ERROR", "CANCELED", "SKIPPED"}


def _get_failed_task_logs(run: object, namespace: str) -> str:
    """Best-effort: tail logs from the pod(s) of the first failed KFP task."""
    try:
        task_details = (
            getattr(getattr(run, "run_details", None), "task_details", None) or []
        )
        for task in task_details:
            if "FAIL" not in str(getattr(task, "state", "")).upper():
                continue
            task_name = getattr(task, "display_name", "unknown-task")
            for ct in getattr(task, "child_tasks", None) or []:
                pod = (
                    ct.get("pod_name")
                    if isinstance(ct, dict)
                    else getattr(ct, "pod_name", None)
                )
                if not pod:
                    continue
                for container in ("main", "user-main"):
                    result = subprocess.run(
                        [
                            "kubectl",
                            "logs",
                            pod,
                            "-n",
                            namespace,
                            "-c",
                            container,
                            "--tail=15",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        header = f"[Task '{task_name}' / pod {pod[:30]}...]"
                        tail = "\n".join(
                            f"  {l}" for l in result.stdout.strip().splitlines()[-10:]
                        )
                        return f"{header}\n{tail}"
    except Exception:  # noqa: BLE001
        pass
    return ""


def _poll_kfp_run(run_id: str, timeout: int, interval: int = 30) -> tuple[str, str]:
    """Poll a KFP run until terminal state. Returns (status, error_detail)."""
    try:
        from kfp.client import Client
    except ImportError:
        return "SKIP (kfp not installed)", ""
    client = Client()
    try:
        with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace") as fh:
            namespace = fh.read().strip()
    except OSError:
        namespace = ""
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get_run(run_id)
        state = str(
            getattr(run, "state", None)
            or getattr(getattr(run, "run", None), "status", None)
            or "UNKNOWN"
        ).upper()
        if state in _KFP_TERMINAL_STATES:
            error_detail = ""
            if state not in ("SUCCEEDED", "SKIPPED"):
                err = getattr(run, "error", None)
                error_detail = (getattr(err, "message", "") or "") if err else ""
                if not error_detail and namespace:
                    error_detail = _get_failed_task_logs(run, namespace)
            return state, error_detail
        time.sleep(interval)
    return f"TIMEOUT after {timeout}s", ""


def _run_cleanup(cleanup_path: Path) -> None:
    """Run a cleanup.py; log but don't raise on failure."""
    try:
        subprocess.run(
            [sys.executable, str(cleanup_path)],
            capture_output=True,
            text=True,
            cwd=str(cleanup_path.parent),
            timeout=120,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  WARNING: cleanup {cleanup_path.name} failed: {exc}", file=sys.stderr)


# ── Orchestration context ─────────────────────────────────────────────────────


@dataclass
class _Context:
    """Shared mutable state threaded through every phase."""

    executor: ThreadPoolExecutor
    root: Path
    output_dir: Path
    timeout_notebook: int
    timeout_pipeline: int
    results: dict[str, Result]
    poll_results: dict[str, str]
    poll_errors: dict[str, str]


# ── Execution primitives ──────────────────────────────────────────────────────


def _make_work(
    steps: list[Step], root: Path, output_dir: Path, timeout: int
) -> Callable[[Result], None]:
    """Build a work(result) closure from a list of Steps."""

    def work(result: Result) -> None:
        for step in steps:
            if step.kind == "notebook":
                out = _run_notebook(root / step.path, output_dir, timeout)
                if step.extract_run_ids:
                    result.kfp_run_ids.extend(_extract_run_ids_from_notebook(out))
            elif step.kind == "script":
                stdout, _ = _run_script(
                    root / step.path,
                    timeout,
                    extra_args=step.extra_args or None,
                )
                if step.extract_run_ids:
                    result.kfp_run_ids.extend(_extract_run_ids_from_stdout(stdout))

    return work


def _timed_run(
    executor: ThreadPoolExecutor,
    results: dict[str, Result],
    name: str,
    work: Callable[[Result], None],
) -> Future:
    """Submit work(result) to the executor with shared timing + error handling."""
    result = Result(name=name)
    results[name] = result
    print(f"  [START  ] {name}")

    def _run() -> None:
        t0 = time.time()
        try:
            work(result)
            result.status = "PASS"
        except Exception as exc:  # noqa: BLE001
            result.status = "FAIL"
            result.error = str(exc)
        finally:
            result.duration = time.time() - t0

    return executor.submit(_run)


def _drain(ctx: _Context, futures: dict[str, Future]) -> None:
    """Wait on a {name: Future} map, printing each result as it completes."""
    by_future = {v: k for k, v in futures.items()}
    for f in as_completed(futures.values()):
        _print_result(ctx.results[by_future[f]])


def _skip(ctx: _Context, name: str, reason: str) -> None:
    """Record a SKIP result and print a one-line notice."""
    print(f"  [SKIP  ] {name}")
    ctx.results[name] = Result(name=name, status="SKIP", error=reason)


# ── Report ────────────────────────────────────────────────────────────────────


def _print_result(r: Result) -> None:
    dur = f"{r.duration:.0f}s" if r.duration else "-"
    print(f"  [{r.status}] {r.name}  ({dur})")
    if r.status == "FAIL" and r.error:
        for line in r.error.splitlines():
            print(f"         {line}")


def _print_report(
    results: dict[str, Result],
    poll_results: dict[str, str],
    poll_errors: dict[str, str],
    run_id_to_name: dict[str, str],
) -> None:
    col = 50
    passed = failed = 0
    for r in results.values():
        if r.status == "FAIL":
            failed += 1
        else:
            passed += 1
    for status in poll_results.values():
        if status.upper() == "SUCCEEDED":
            passed += 1
        else:
            failed += 1

    if failed:
        print("\nFailed details:")
        print("-" * 70)
        for r in results.values():
            if r.status == "FAIL" and r.error:
                print(f"\n{r.name}:")
                for line in r.error.splitlines():
                    print(f"  {line}")
        for run_id, status in poll_results.items():
            if status.upper() != "SUCCEEDED":
                source = run_id_to_name.get(run_id, "unknown")
                print(f"\nKFP run {run_id[:8]}... (from {source}): {status}")
                err = poll_errors.get(run_id, "")
                if err:
                    for line in err.splitlines():
                        print(f"  {line}")

    print("\n" + "=" * 70)
    print(f"{'EXAMPLE':<{col}} {'STATUS':<10} {'DURATION'}")
    print("-" * 70)
    for r in results.values():
        dur = f"{r.duration:.0f}s" if r.duration else "-"
        print(f"{r.name:<{col}} {r.status:<10} {dur}")
    if poll_results:
        print()
        print(f"{'KFP RUN (source notebook)':<{col}} {'STATUS':<10}")
        print("-" * 70)
        for run_id, status in poll_results.items():
            source = run_id_to_name.get(run_id, "unknown")
            label = f"{run_id[:8]}... ({source})"
            print(f"{label:<{col}} {status:<10}")
    print("=" * 70)
    print(f"PASSED: {passed}   FAILED: {failed}   TOTAL: {passed + failed}")
    print()


def _print_dry_run() -> None:
    by_phase: dict[int, list[str]] = {}
    for ex in _EXAMPLES:
        label = ex.name
        if ex.opt_in:
            label += f"  (--{ex.opt_in.replace('_', '-')})"
        if ex.mlflow_dependent:
            label += "  (mlflow)"
        by_phase.setdefault(ex.phase, []).append(label)
    phase_names = {
        1: "independent",
        2: "pipeline submissions",
        3: "MLflow KServe ISVCs",
    }
    print("[dry-run] Would execute the following phases:")
    for phase, labels in sorted(by_phase.items()):
        print(f"  Phase {phase} ({phase_names.get(phase, f'phase {phase}')}):")
        for label in labels:
            print(f"    {label}")
    print("  Phase 4: KFP run polling")
    print("  Phase 5: cleanup")


# ── Pre-flight ────────────────────────────────────────────────────────────────


def _check_mlflow_credentials() -> tuple[bool, str]:
    """Return (ok, reason). Checks secret existence then validates with MLflow API."""
    import base64 as _b64
    import json as _json
    import urllib.error
    import urllib.request

    ns = _namespace()
    r = subprocess.run(
        ["kubectl", "get", "secret", "mlflow-credentials", "-n", ns, "-o", "json"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return False, (
            "mlflow-credentials secret not found — "
            "run scripts/setup_mlflow_credentials.py first"
        )
    try:
        data = _json.loads(r.stdout)["data"]
        uri = _b64.b64decode(data["MLFLOW_TRACKING_URI"]).decode().rstrip("/")
        username = _b64.b64decode(data["MLFLOW_TRACKING_USERNAME"]).decode()
        password = _b64.b64decode(data["MLFLOW_TRACKING_PASSWORD"]).decode()
    except KeyError as exc:
        return (
            False,
            f"mlflow-credentials secret is missing key {exc} — re-run setup_mlflow_credentials.py",
        )

    creds = _b64.b64encode(f"{username}:{password}".encode()).decode()
    req = urllib.request.Request(
        f"{uri}/api/2.0/mlflow/experiments/search?max_results=1",
        headers={"Authorization": f"Basic {creds}"},
    )
    try:
        urllib.request.urlopen(req, timeout=8)
        return True, "OK"
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return False, (
                "MLflow credentials are invalid or the PAT has expired — "
                "re-run scripts/setup_mlflow_credentials.py"
            )
        return (
            False,
            f"MLflow API returned HTTP {exc.code} — check MLFLOW_TRACKING_URI in the secret",
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"Could not reach MLflow at {uri}: {exc}"


def _preflight(results: dict[str, Result]) -> bool:
    """Install papermill and validate MLflow credentials.

    MLflow-dependent examples are recorded as SKIP in `results` on failure.
    Returns True if MLflow credentials are valid.
    """
    _ensure_papermill()
    print("Pre-flight: checking MLflow credentials...")
    mlflow_ok, reason = _check_mlflow_credentials()
    if mlflow_ok:
        print("  [OK] MLflow credentials valid")
    else:
        print(f"  [SKIP] {reason}")
        for ex in _EXAMPLES:
            if ex.mlflow_dependent:
                results[ex.name] = Result(name=ex.name, status="SKIP", error=reason)
    return mlflow_ok


# ── Phases ────────────────────────────────────────────────────────────────────


def _run_phase(
    ctx: _Context,
    phase: int,
    opts: dict[str, bool],
) -> dict[str, Future]:
    """Submit all examples for a given phase; return {name: Future}."""
    futures: dict[str, Future] = {}
    for ex in _EXAMPLES:
        if ex.phase != phase:
            continue
        if ex.name in ctx.results:  # already SKIP from pre-flight
            print(f"  [SKIP  ] {ex.name}")
            continue
        if ex.opt_in and not opts.get(ex.opt_in, False):
            _skip(
                ctx, ex.name, f"opt-in: pass --{ex.opt_in.replace('_', '-')} to enable"
            )
            continue
        work = _make_work(ex.steps, ctx.root, ctx.output_dir, ctx.timeout_notebook)
        futures[ex.name] = _timed_run(ctx.executor, ctx.results, ex.name, work)
    return futures


def _await_mobile_price(ctx: _Context, phase2_futures: dict[str, Future]) -> bool:
    """Wait for mlflow-mobile-price and poll its KFP run inline.

    Phase 3 ISVCs need the registered model, so this must complete before
    Phase 3 starts. Returns True if the model is registered and ready.
    """
    name = "mlflow/mobile-price-classification"
    if name not in phase2_futures:
        return False

    phase2_futures[name].result()
    _print_result(ctx.results[name])
    if ctx.results[name].status != "PASS":
        return False

    run_ids = ctx.results[name].kfp_run_ids
    if not run_ids:
        return True

    print(
        "  Polling mlflow-mobile-price KFP pipeline (model must be registered before ISVCs)..."
    )
    ok = True
    for run_id in run_ids:
        state, err = _poll_kfp_run(run_id, ctx.timeout_pipeline)
        ctx.poll_results[run_id] = state
        ctx.poll_errors[run_id] = err
        print(f"    [{state}] {run_id[:8]}...")
        if state.upper() != "SUCCEEDED":
            ok = False
    return ok


def _phase4_poll(ctx: _Context) -> None:
    all_run_ids = [
        rid
        for r in ctx.results.values()
        for rid in r.kfp_run_ids
        if rid not in ctx.poll_results
    ]
    if not all_run_ids:
        print("\nPhase 4: no KFP run IDs found, skipping poll.")
        return

    print(f"\nPhase 4: polling {len(all_run_ids)} KFP run(s)...")
    poll_futures = {
        run_id: ctx.executor.submit(_poll_kfp_run, run_id, ctx.timeout_pipeline)
        for run_id in all_run_ids
    }
    for run_id, f in poll_futures.items():
        try:
            ctx.poll_results[run_id], ctx.poll_errors[run_id] = f.result()
        except Exception as exc:  # noqa: BLE001
            ctx.poll_results[run_id] = f"POLL_ERROR: {exc}"
            ctx.poll_errors[run_id] = ""
        print(f"  [{ctx.poll_results[run_id]}] {run_id[:8]}...")


def _phase5_cleanup(cleanup_scripts: list[Path]) -> None:
    print("\nPhase 5: running cleanup scripts...")
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(_run_cleanup, p) for p in cleanup_scripts if p.exists()]
        for f in as_completed(futs):
            f.result()


# ── Main ──────────────────────────────────────────────────────────────────────


def run_all(
    timeout_notebook: int = 1800,
    timeout_pipeline: int = 3600,
    include_keda: bool = False,
    include_pytorch: bool = False,
    include_shadow: bool = False,
    dry_run: bool = False,
) -> dict[str, Result]:
    root = _REPO_ROOT
    results: dict[str, Result] = {}

    if dry_run:
        _print_dry_run()
        return results

    _preflight(results)

    opts = {
        "include_keda": include_keda,
        "include_pytorch": include_pytorch,
        "include_shadow": include_shadow,
    }
    cleanup_scripts = [root / ex.cleanup for ex in _EXAMPLES if ex.cleanup] + [
        root / p for p in _EXTRA_CLEANUP_PATHS
    ]
    poll_results: dict[str, str] = {}
    poll_errors: dict[str, str] = {}

    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            ctx = _Context(
                executor=executor,
                root=root,
                output_dir=root / "ci" / "output",
                timeout_notebook=timeout_notebook,
                timeout_pipeline=timeout_pipeline,
                results=results,
                poll_results=poll_results,
                poll_errors=poll_errors,
            )

            print("Phase 1: running independent examples in parallel...")
            _drain(ctx, _run_phase(ctx, 1, opts))

            print("\nPhase 2: submitting pipelines...")
            phase2_futures = _run_phase(ctx, 2, opts)
            mobile_price_ok = _await_mobile_price(ctx, phase2_futures)

            print("\nPhase 3: deploying MLflow KServe InferenceServices...")
            if mobile_price_ok:
                phase3_futures = _run_phase(ctx, 3, opts)
            else:
                skipped = "mlflow/mobile-price-classification" not in phase2_futures
                reason = (
                    "prerequisite mlflow/mobile-price-classification skipped (MLflow credentials)"
                    if skipped
                    else "prerequisite mlflow/mobile-price-classification notebook or KFP pipeline did not succeed"
                )
                print(f"  [SKIP] {reason}")
                for ex in _EXAMPLES:
                    if ex.phase == 3:
                        ctx.results[ex.name] = Result(
                            name=ex.name, status="SKIP", error=reason
                        )
                phase3_futures = {}

            print("\nPhase 2 (remaining) + Phase 3 running concurrently...")
            remaining = {
                k: v
                for k, v in phase2_futures.items()
                if k != "mlflow/mobile-price-classification"
            }
            remaining.update(phase3_futures)
            _drain(ctx, remaining)

            _phase4_poll(ctx)

    finally:
        _phase5_cleanup(cleanup_scripts)

    run_id_to_name = {
        run_id: r.name for r in results.values() for run_id in r.kfp_run_ids
    }
    _print_report(results, poll_results, poll_errors, run_id_to_name)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--timeout-notebook",
        type=int,
        default=1800,
        help="Per-notebook execution timeout in seconds (default: 1800)",
    )
    parser.add_argument(
        "--timeout-pipeline",
        type=int,
        default=3600,
        help="KFP run poll timeout in seconds (default: 3600)",
    )
    parser.add_argument(
        "--include-keda",
        action="store_true",
        help="Include KEDA autoscaling example (opt-in; requires KEDA in the cluster; runs on CPU)",
    )
    parser.add_argument(
        "--include-shadow",
        action="store_true",
        help=(
            "Include minimal-example-shadow-deployment (opt-in; "
            "requires CrunchyData postgres-operator; Istio VirtualService not tested)"
        ),
    )
    parser.add_argument(
        "--include-pytorch",
        action="store_true",
        help="Include pytorch_lightning examples (opt-in; requires pytorch in the notebook image)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan without executing anything",
    )
    args = parser.parse_args()

    results = run_all(
        timeout_notebook=args.timeout_notebook,
        timeout_pipeline=args.timeout_pipeline,
        include_keda=args.include_keda,
        include_shadow=args.include_shadow,
        include_pytorch=args.include_pytorch,
        dry_run=args.dry_run,
    )

    failed = sum(1 for r in results.values() if r.status == "FAIL")
    sys.exit(1 if failed else 0)
