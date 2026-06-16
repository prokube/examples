"""
CI orchestrator — runs all automatable examples and reports results.

Execution model
---------------
Phase 1 (parallel, self-contained):
    notebooks/dask/dask_example.ipynb
    mlflow/mlflow-quickstart-example.ipynb
    mlflow/mlflow-image-example.ipynb
    mlflow/mlflow-kfp-example.ipynb
    serving/minimal-s3-model/minimal-s3-model.ipynb

Phase 2 (parallel, pipeline submissions — return fast):
    mlflow/mobile-price-classification/mlflow-mobile-price-classification.ipynb
    pipelines/lightweight-components/mobile-price-classifications.ipynb
    pipelines/lightweight-python-package/submit-cluster.py   (Python script)

Phase 3 (depends on Phase 2 mlflow-mobile-price notebook completing):
    serving/mlflow-kserve-minimal/apply.py + test_inference_service.py
    serving/mlflow-kserve-inference-protocols/inference_protocol_version_example.ipynb

Phase 4 (KFP run polling — runs alongside Phase 3):
    Poll all KFP run IDs extracted from Phase 2 output notebooks until
    Succeeded or timeout.

Phase 5 — cleanup (always, in finally block):
    All cleanup.py scripts in parallel.

Usage from a Jupyter notebook
------------------------------
    import subprocess
    subprocess.run(["python", "ci/run_all.py"], check=True)

CLI usage
---------
    python ci/run_all.py [--timeout-notebook 1800] [--timeout-pipeline 3600]
                         [--include-keda] [--dry-run]

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
from typing import Callable


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
    # Show the failing cell source (first 5 lines)
    if exc.source:
        src_lines = exc.source.strip().splitlines()[:5]
        lines.append("  Cell source:")
        for src_line in src_lines:
            lines.append(f"    {src_line}")
        if len(exc.source.strip().splitlines()) > 5:
            lines.append("    ...")
    # Show the innermost traceback frame (last non-empty line)
    if exc.traceback:
        tb_lines = [l for l in exc.traceback if l.strip()]
        if tb_lines:
            lines.append(f"  Traceback (last): {tb_lines[-1].strip()}")
    return "\n".join(lines)


def _strip_ci_skip_cells(nb_path: Path, output_dir: Path) -> Path:
    """Return a copy of the notebook with 'ci-skip' tagged cells replaced by a comment.
    Returns the original path unchanged if no cells are tagged."""
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
            cwd=str(nb_path.parent),  # always cwd to original notebook directory
            progress_bar=False,  # avoid interleaved tqdm bars from parallel threads
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
    return list(dict.fromkeys(ids))  # deduplicate, preserve order


def _extract_run_ids_from_stdout(stdout: str) -> list[str]:
    """Parse stdout from a script for KFP_RUN_ID=<uuid> lines."""
    ids = []
    for line in stdout.splitlines():
        if line.startswith("KFP_RUN_ID="):
            ids.append(line.split("=", 1)[1].strip())
    return ids


_KFP_TERMINAL_STATES = {"SUCCEEDED", "FAILED", "ERROR", "CANCELED", "SKIPPED"}


def _get_failed_task_logs(run: object, namespace: str) -> str:
    """Best-effort: tail logs from the pod(s) of the first failed KFP task.

    Walks run.run_details.task_details → child_tasks → pod_name and tries
    kubectl logs on those pods.  Silently returns "" on any failure.
    """
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
        # KFP v2 SDK: state is on the run object directly as a string
        # KFP v1 SDK: state is on run.run.status
        state = str(
            getattr(run, "state", None)
            or getattr(getattr(run, "run", None), "status", None)
            or "UNKNOWN"
        ).upper()
        if state in _KFP_TERMINAL_STATES:
            error_detail = ""
            if state not in ("SUCCEEDED", "SKIPPED"):
                # run.error is often None even for failed runs in KFP v2 —
                # the real failure is in the task pod logs
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


# ── Executor ──────────────────────────────────────────────────────────────────


def _timed_run(
    executor: ThreadPoolExecutor,
    results: dict[str, Result],
    name: str,
    work: Callable[[Result], None],
) -> Future:
    """Submit `work(result)` to the executor with shared timing + error handling.

    `work` mutates the Result (e.g. sets kfp_run_ids); status/duration are set
    here. The first exception is recorded as FAIL.
    """
    result = Result(name=name)
    results[name] = result
    print(f"  [START  ] {name}")

    def _run():
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


def _submit_notebook(
    executor: ThreadPoolExecutor,
    results: dict[str, Result],
    name: str,
    nb_path: Path,
    output_dir: Path,
    timeout: int,
    extract_run_ids: bool = True,
) -> Future:
    def work(result: Result) -> None:
        out = _run_notebook(nb_path, output_dir, timeout)
        if extract_run_ids:
            result.kfp_run_ids = _extract_run_ids_from_notebook(out)

    return _timed_run(executor, results, name, work)


def _submit_script(
    executor: ThreadPoolExecutor,
    results: dict[str, Result],
    name: str,
    script_path: Path,
    timeout: int,
    extra_args: list[str] | None = None,
) -> Future:
    def work(result: Result) -> None:
        stdout, _ = _run_script(script_path, timeout, extra_args=extra_args)
        result.kfp_run_ids = _extract_run_ids_from_stdout(stdout)

    return _timed_run(executor, results, name, work)


def _submit_chain(
    executor: ThreadPoolExecutor,
    results: dict[str, Result],
    name: str,
    steps: list[tuple[str, Path | None, dict]],
    output_dir: Path,
    timeout: int,
) -> Future:
    """Submit a sequential chain of (kind, path, kwargs) steps as a single named result.

    kind is 'notebook' or 'script'.  kwargs may include 'extra_args' for scripts.
    All steps run in one thread; the first failure stops the chain.
    """

    def work(result: Result) -> None:
        for kind, path, kwargs in steps:
            if kind == "notebook":
                out = _run_notebook(path, output_dir, timeout)
                result.kfp_run_ids.extend(_extract_run_ids_from_notebook(out))
            elif kind == "script":
                stdout, _ = _run_script(
                    path, timeout, extra_args=kwargs.get("extra_args")
                )
                result.kfp_run_ids.extend(_extract_run_ids_from_stdout(stdout))
            elif kind == "pip":
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-q"]
                    + kwargs.get("packages", []),
                    capture_output=True,
                    text=True,
                    check=True,
                )

    return _timed_run(executor, results, name, work)


# ── Report ────────────────────────────────────────────────────────────────────


def _print_result(r: Result) -> None:
    """Print a single result line, with error detail if failed."""
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
    for run_id, status in poll_results.items():
        if status.upper() == "SUCCEEDED":
            passed += 1
        else:
            failed += 1

    # Failed details first so they're easy to scroll back to
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

    # Summary table last — easy to see final verdict at a glance
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


# ── MLflow pre-flight check ───────────────────────────────────────────────────

# Notebooks that require working MLflow credentials
_MLFLOW_DEPENDENT = frozenset(
    {
        "mlflow/mlflow-quickstart",
        "mlflow/mlflow-image-example",
        "mlflow/mlflow-kfp-example",
        "mlflow/mobile-price-classification",
    }
)


def _check_mlflow_credentials() -> tuple[bool, str]:
    """Return (ok, reason).  Checks secret existence then validates credentials
    with a quick call to the MLflow REST API."""
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


_CLEANUP_RELPATHS = [
    "notebooks/dask/cleanup.py",
    "serving/minimal-s3-model/cleanup.py",
    "serving/mlflow-kserve-minimal/cleanup.py",
    "serving/mlflow-kserve-inference-protocols/cleanup.py",
    "serving/hf-vllm-completion/cleanup.py",
    "serving/kserve-keda-autoscaling/cleanup.py",
    "serving/minimal-example-shadow-deployment/cleanup.py",
    "hparam-tuning/minimal-mnist/cleanup.py",
]

_DRY_RUN_PHASES = [
    "Phase 1: dask, mlflow-quickstart, mlflow-image, mlflow-kfp, minimal-s3-model, hf-vllm-completion",
    "Phase 1 (opt-in): kserve-keda-autoscaling (--include-keda), minimal-example-shadow-deployment (--include-shadow)",
    "Phase 2: mlflow-mobile-price, lightweight-components, lightweight-python-package",
    "Phase 3: mlflow-kserve-minimal, mlflow-kserve-inference-protocols",
    "Phase 4: KFP run polling",
    "Phase 5: cleanup",
]


def _drain(ctx: _Context, futures: dict[str, Future]) -> None:
    """Wait on a {name: Future} map, printing each result as it completes."""
    by_future = {v: k for k, v in futures.items()}
    for f in as_completed(futures.values()):
        _print_result(ctx.results[by_future[f]])


def _skip(ctx: _Context, name: str, reason: str, label: str | None = None) -> None:
    """Record a SKIP result and print a one-line notice."""
    print(f"  [SKIP  ] {label or name}")
    ctx.results[name] = Result(name=name, status="SKIP", error=reason)


# ── Pre-flight ────────────────────────────────────────────────────────────────


def _preflight(results: dict[str, Result]) -> tuple[bool, str]:
    """Ensure papermill, then validate MLflow credentials.

    Returns (mlflow_ok, reason). On failure, MLflow-dependent examples are
    recorded as SKIP in `results`.
    """
    _ensure_papermill()
    print("Pre-flight: checking MLflow credentials...")
    mlflow_ok, mlflow_reason = _check_mlflow_credentials()
    if mlflow_ok:
        print("  [OK] MLflow credentials valid")
    else:
        print(f"  [SKIP] {mlflow_reason}")
        for name in _MLFLOW_DEPENDENT:
            results[name] = Result(name=name, status="SKIP", error=mlflow_reason)
    return mlflow_ok, mlflow_reason


# ── Phases ──────────────────────────────────────────────────────────────────


def _phase1(
    ctx: _Context,
    include_keda: bool,
    include_shadow: bool,
    include_pytorch: bool,
) -> None:
    """Phase 1: independent notebooks + self-contained serving examples."""
    print("Phase 1: running independent notebooks in parallel...")
    futures: dict[str, Future] = {}
    for name, rel in [
        ("notebooks/dask", "notebooks/dask/dask_example.ipynb"),
        (
            "notebooks/mobile-price-classification",
            "notebooks/mobile-price-classification/mobile-price-classifications.ipynb",
        ),
        ("mlflow/mlflow-quickstart", "mlflow/mlflow-quickstart-example.ipynb"),
        ("mlflow/mlflow-image-example", "mlflow/mlflow-image-example.ipynb"),
        ("mlflow/mlflow-kfp-example", "mlflow/mlflow-kfp-example.ipynb"),
        ("serving/minimal-s3-model", "serving/minimal-s3-model/minimal-s3-model.ipynb"),
    ]:
        if name in ctx.results:  # already SKIP from pre-flight
            print(f"  [SKIP  ] {name}")
            continue
        futures[name] = _submit_notebook(
            ctx.executor,
            ctx.results,
            name,
            ctx.root / rel,
            ctx.output_dir,
            ctx.timeout_notebook,
        )

    # hf-vllm-completion (CPU): self-contained, no KFP pipelines
    futures["serving/hf-vllm-completion"] = _submit_script(
        ctx.executor,
        ctx.results,
        "serving/hf-vllm-completion",
        ctx.root / "serving" / "hf-vllm-completion" / "apply.py",
        ctx.timeout_notebook,
    )

    # kserve-keda-autoscaling: opt-in; apply.py self-checks KEDA CRDs
    # and exits 0 with a skip message if KEDA is not installed.
    if include_keda:
        futures["serving/kserve-keda-autoscaling"] = _submit_script(
            ctx.executor,
            ctx.results,
            "serving/kserve-keda-autoscaling",
            ctx.root / "serving" / "kserve-keda-autoscaling" / "apply.py",
            ctx.timeout_notebook,
        )
    else:
        _skip(
            ctx,
            "serving/kserve-keda-autoscaling",
            "opt-in: pass --include-keda to run this example",
            label="serving/kserve-keda-autoscaling  (pass --include-keda to enable)",
        )

    # minimal-example-shadow-deployment: opt-in; apply.py self-checks for
    # the postgres-operator CRD and exits 0 if not found. Istio
    # VirtualService mirroring is not verified in CI (requires domain config).
    if include_shadow:
        futures["serving/minimal-example-shadow-deployment"] = _submit_script(
            ctx.executor,
            ctx.results,
            "serving/minimal-example-shadow-deployment",
            ctx.root / "serving" / "minimal-example-shadow-deployment" / "apply.py",
            ctx.timeout_notebook,
        )
    else:
        _skip(
            ctx,
            "serving/minimal-example-shadow-deployment",
            "opt-in: pass --include-shadow to run this example",
            label="serving/minimal-example-shadow-deployment  (pass --include-shadow to enable)",
        )

    # mnist-vae: opt-in (requires pytorch_lightning, not in all images)
    if include_pytorch:
        futures["notebooks/mnist-vae"] = _submit_chain(
            ctx.executor,
            ctx.results,
            "notebooks/mnist-vae",
            steps=[
                # run_training.py self-installs pytorch-lightning if absent
                (
                    "script",
                    ctx.root / "notebooks/mnist-vae/run_training.py",
                    {"extra_args": ["--max_epochs", "3"]},
                ),
                ("notebook", ctx.root / "notebooks/mnist-vae/visualizations.ipynb", {}),
            ],
            output_dir=ctx.output_dir,
            timeout=ctx.timeout_notebook,
        )
    else:
        print("  [SKIP  ] notebooks/mnist-vae  (pass --include-pytorch to enable)")

    _drain(ctx, futures)


def _phase2_submit(ctx: _Context) -> dict[str, Future]:
    """Phase 2: submit pipeline notebooks + scripts (they return fast)."""
    print("\nPhase 2: submitting pipelines...")
    futures: dict[str, Future] = {}
    for name, rel in [
        (
            "mlflow/mobile-price-classification",
            "mlflow/mobile-price-classification/mlflow-mobile-price-classification.ipynb",
        ),
        (
            "pipelines/lightweight-components",
            "pipelines/lightweight-components/mobile-price-classifications.ipynb",
        ),
    ]:
        if name in ctx.results:  # already SKIP from pre-flight
            print(f"  [SKIP  ] {name}")
            continue
        futures[name] = _submit_notebook(
            ctx.executor,
            ctx.results,
            name,
            ctx.root / rel,
            ctx.output_dir,
            ctx.timeout_notebook,
        )

    futures["pipelines/lightweight-python-package"] = _submit_script(
        ctx.executor,
        ctx.results,
        "pipelines/lightweight-python-package",
        ctx.root / "pipelines" / "lightweight-python-package" / "submit-cluster.py",
        ctx.timeout_notebook,
    )
    futures["pipelines/minimal-container-components"] = _submit_script(
        ctx.executor,
        ctx.results,
        "pipelines/minimal-container-components",
        ctx.root / "pipelines" / "minimal-container-components" / "submit-cluster.py",
        ctx.timeout_notebook,
    )
    return futures


def _await_mobile_price(ctx: _Context, phase2_futures: dict[str, Future]) -> bool:
    """Wait for the mlflow-mobile-price notebook and poll its KFP run inline.

    Phase 3 ISVCs need the registered model, so this must complete before
    Phase 3 starts. Returns True if the model is registered and ready.
    """
    name = "mlflow/mobile-price-classification"
    skipped = name not in phase2_futures
    if skipped:
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
        ctx.poll_results[run_id] = state  # recorded here; Phase 4 will skip it
        ctx.poll_errors[run_id] = err
        print(f"    [{state}] {run_id[:8]}...")
        if state.upper() != "SUCCEEDED":
            ok = False
    return ok


def _phase3_submit(
    ctx: _Context, mobile_price_ok: bool, mobile_price_skipped: bool
) -> dict[str, Future]:
    """Phase 3: deploy MLflow KServe InferenceServices (need registered model)."""
    print("\nPhase 3: deploying MLflow KServe InferenceServices...")
    isvc_names = (
        "serving/mlflow-kserve-minimal",
        "serving/mlflow-kserve-inference-protocols",
    )
    if not mobile_price_ok:
        reason = (
            "prerequisite mlflow/mobile-price-classification skipped (MLflow credentials)"
            if mobile_price_skipped
            else "prerequisite mlflow/mobile-price-classification notebook or KFP pipeline did not succeed"
        )
        print(f"  [SKIP] {reason}")
        for name in isvc_names:
            ctx.results[name] = Result(name=name, status="SKIP", error=reason)
        return {}

    futures: dict[str, Future] = {}
    # mlflow-kserve-minimal: deploy then immediately smoke-test
    # deploy_and_test() in apply.py handles both steps
    futures["serving/mlflow-kserve-minimal"] = _submit_script(
        ctx.executor,
        ctx.results,
        "serving/mlflow-kserve-minimal",
        ctx.root / "serving" / "mlflow-kserve-minimal" / "apply.py",
        ctx.timeout_notebook,
    )
    # inference-protocols notebook handles its own deploy + test.
    # extract_run_ids=False: this notebook is not a pipeline submission;
    # its output contains ISVC/request UUIDs that must not be polled
    # as KFP run IDs (they return 404 from the KFP API).
    futures["serving/mlflow-kserve-inference-protocols"] = _submit_notebook(
        ctx.executor,
        ctx.results,
        "serving/mlflow-kserve-inference-protocols",
        ctx.root
        / "serving/mlflow-kserve-inference-protocols/inference_protocol_version_example.ipynb",
        ctx.output_dir,
        ctx.timeout_notebook,
        extract_run_ids=False,
    )
    return futures


def _phase4_poll(ctx: _Context) -> None:
    """Phase 4: poll all KFP run IDs not already polled inline before Phase 3."""
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
    """Phase 5: run all cleanup scripts in parallel (always, even on failure)."""
    print("\nPhase 5: running cleanup scripts...")
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(_run_cleanup, p) for p in cleanup_scripts if p.exists()]
        for f in as_completed(futs):
            f.result()  # already swallows exceptions inside _run_cleanup


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

    mlflow_ok, _ = _preflight(results)
    if not mlflow_ok and dry_run:
        print("[dry-run] Would execute the following phases:")
        for label in _DRY_RUN_PHASES:
            print(f"  {label}")
        return results

    cleanup_scripts = [root / rel for rel in _CLEANUP_RELPATHS]
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

            _phase1(ctx, include_keda, include_shadow, include_pytorch)
            phase2_futures = _phase2_submit(ctx)

            mobile_price_skipped = (
                "mlflow/mobile-price-classification" not in phase2_futures
            )
            mobile_price_ok = _await_mobile_price(ctx, phase2_futures)
            phase3_futures = _phase3_submit(ctx, mobile_price_ok, mobile_price_skipped)

            # Phase 2 remaining + phase 3 run concurrently; print as each finishes
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

    # Build run_id → source notebook name map from all results
    run_id_to_name: dict[str, str] = {}
    for r in results.values():
        for run_id in r.kfp_run_ids:
            run_id_to_name[run_id] = r.name

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
        help="Include KEDA autoscaling example (opt-in; requires KEDA installed in the cluster)",
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
        "--dry-run", action="store_true", help="Print plan without executing anything"
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
