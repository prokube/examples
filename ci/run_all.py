"""Run registered examples by phase, poll KFP runs, and always clean up."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal


# ── Repo root ─────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[1]


# ── CI dependencies ───────────────────────────────────────────────────────────


def _require_ci_dependencies() -> None:
    """Fail before starting work if the CI-only dependencies are unavailable."""
    try:
        import papermill  # noqa: F401
        from kfp.client import Client  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "CI dependencies are missing. Install them with "
            f'`python -m pip install -e "{_REPO_ROOT}[ci]"`.'
        ) from exc


def _ensure_pk_helpers() -> None:
    """Editable-install the pk_helpers package if it is not importable.

    Notebooks and serving apply.py scripts import shared prokube helpers via
    ``from pk_helpers import ...``. Installing the repo editable makes the same
    interpreter used by the CI subprocesses able to resolve those imports.
    """
    try:
        import pk_helpers  # noqa: F401
    except ImportError:
        print("pk_helpers not found — installing repo editable...")
        # --user outside a virtualenv (e.g. in a Kubeflow notebook pod) so the
        # install lands under the persistent $HOME/.local instead of the
        # container image's site-packages, which is wiped on the next pod
        # restart. pip rejects --user inside a virtualenv, hence the guard.
        user_flag = [] if sys.prefix != sys.base_prefix else ["--user"]
        subprocess.run(
            [sys.executable, "-m", "pip", "install", *user_flag, "-e", str(_REPO_ROOT)],
            check=True,
        )
        print("pk_helpers installed.")


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
    api_key_dependent: bool = (
        False  # skip automatically when INFERENCE_SERVICE_API_KEY is unset
    )
    env_mutating: bool = False  # run first; modifies the shared Python environment


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
_EXTRA_CLEANUP_PATHS: list[str] = []


# ── Helpers ───────────────────────────────────────────────────────────────────


def _namespace() -> str:
    with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace") as fh:
        return fh.read().strip()


class _CancellationRequested(Exception):
    pass


def _stop_process(proc: subprocess.Popen[str]) -> tuple[str, str]:
    """Interrupt a subprocess group, then kill it if it does not exit promptly."""
    try:
        os.killpg(proc.pid, signal.SIGINT)
    except ProcessLookupError:
        pass
    try:
        return proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        return proc.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        # A grandchild can inherit the stdout/stderr pipe fds and keep them
        # open after the direct child is dead, which makes communicate()
        # block forever waiting for EOF even though SIGKILL was delivered.
        # Close our end and fall back to wait(), which only waits on the
        # pid's exit status, so a stuck example can't hang the whole run.
        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            pass
        return "", ""


def _run_process(
    cmd: list[str],
    cwd: Path,
    cancel_event: threading.Event,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a cancellable process and reap its process group before returning."""
    if cancel_event.is_set():
        raise _CancellationRequested()
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    deadline = time.monotonic() + timeout if timeout is not None else None
    while True:
        if cancel_event.is_set():
            _stop_process(proc)
            raise _CancellationRequested()
        if deadline is not None and time.monotonic() >= deadline:
            stdout, stderr = _stop_process(proc)
            detail = (stderr or stdout or "(no output)").strip()
            raise RuntimeError(f"Timed out after {timeout}s: {detail}")
        try:
            stdout, stderr = proc.communicate(timeout=0.5)
            return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            pass


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


def _run_notebook(
    nb_path: Path,
    output_dir: Path,
    timeout: int,
    root: Path,
    cancel_event: threading.Event,
) -> Path:
    """Execute a notebook with papermill, in-process. Returns the output notebook path.

    In-process (not `python -m papermill` as a subprocess): see commit
    message for the ~75MB/notebook memory reason. Cancellation is only
    checked before start, not mid-run — execution_timeout still hard-stops
    a stuck cell either way.

    Output notebooks are nested under their path relative to `root` (not
    just the basename) so two examples with same-named notebooks — e.g.
    notebooks/mobile-price-classification/ and
    pipelines/lightweight-components/, both mobile-price-classifications.ipynb
    — don't overwrite each other's output.
    """
    if cancel_event.is_set():
        raise _CancellationRequested()

    import papermill as pm
    from papermill.exceptions import PapermillExecutionError

    output_dir = output_dir / nb_path.parent.relative_to(root)
    output_dir.mkdir(parents=True, exist_ok=True)
    nb_to_run = _strip_ci_skip_cells(nb_path, output_dir)
    output_path = output_dir / nb_path.name
    try:
        pm.execute_notebook(
            str(nb_to_run),
            str(output_path),
            kernel_name="python3",
            execution_timeout=timeout,
            resources={"metadata": {"path": str(nb_path.parent)}},
            progress_bar=False,
        )
    except PapermillExecutionError as exc:
        raise RuntimeError(_format_papermill_error(exc)) from exc
    return output_path


def _run_script(
    script_path: Path,
    timeout: int,
    cancel_event: threading.Event,
    extra_args: list[str] | None = None,
) -> tuple[str, str]:
    """Run a plain Python script. Returns (stdout, stderr)."""
    cmd = [sys.executable, str(script_path)] + (extra_args or [])
    result = _run_process(
        cmd,
        cwd=script_path.parent,
        cancel_event=cancel_event,
        timeout=timeout,
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


def _poll_kfp_run(
    run_id: str,
    timeout: int,
    cancel_event: threading.Event,
    interval: int = 30,
) -> tuple[str, str]:
    """Poll a KFP run until terminal state. Returns (status, error_detail)."""
    from kfp.client import Client

    client = Client()
    try:
        with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace") as fh:
            namespace = fh.read().strip()
    except OSError:
        namespace = ""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cancel_event.is_set():
            raise _CancellationRequested()
        run = client.get_run(run_id)
        if cancel_event.is_set():
            raise _CancellationRequested()
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
        remaining = deadline - time.monotonic()
        if remaining > 0 and cancel_event.wait(min(interval, remaining)):
            raise _CancellationRequested()
    return f"TIMEOUT after {timeout}s", ""


def _run_cleanup(cleanup_path: Path) -> None:
    """Run a cleanup.py; log but don't raise on failure."""
    try:
        result = subprocess.run(
            [sys.executable, str(cleanup_path)],
            capture_output=True,
            text=True,
            cwd=str(cleanup_path.parent),
            timeout=120,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "(no output)").strip()
            print(
                f"  WARNING: cleanup {cleanup_path.name} exited "
                f"{result.returncode}: {detail}",
                file=sys.stderr,
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
    cancel_event: threading.Event
    running: set[str] = field(default_factory=set)
    running_lock: threading.Lock = field(default_factory=threading.Lock)


# ── Execution primitives ──────────────────────────────────────────────────────


def _make_work(
    steps: list[Step],
    root: Path,
    output_dir: Path,
    timeout: int,
    cancel_event: threading.Event,
) -> Callable[[Result], None]:
    """Build a work(result) closure from a list of Steps."""

    def work(result: Result) -> None:
        for step in steps:
            if cancel_event.is_set():
                raise _CancellationRequested()
            if step.kind == "notebook":
                out = _run_notebook(
                    root / step.path, output_dir, timeout, root, cancel_event
                )
                if step.extract_run_ids:
                    result.kfp_run_ids.extend(_extract_run_ids_from_notebook(out))
            elif step.kind == "script":
                stdout, _ = _run_script(
                    root / step.path,
                    timeout,
                    cancel_event,
                    extra_args=step.extra_args or None,
                )
                if step.extract_run_ids:
                    result.kfp_run_ids.extend(_extract_run_ids_from_stdout(stdout))

    return work


def _timed_run(
    ctx: _Context,
    name: str,
    work: Callable[[Result], None],
) -> Future:
    """Submit work(result) to the executor with shared timing + error handling."""
    result = Result(name=name)
    ctx.results[name] = result
    print(f"  [START  ] {name}")

    def _run() -> None:
        t0 = time.time()
        with ctx.running_lock:
            ctx.running.add(name)
        try:
            work(result)
            result.status = "PASS"
        except _CancellationRequested:
            result.status = "SKIP"
            result.error = "cancelled"
        except Exception as exc:  # noqa: BLE001
            result.status = "FAIL"
            result.error = str(exc)
        finally:
            result.duration = time.time() - t0
            with ctx.running_lock:
                ctx.running.discard(name)

    return ctx.executor.submit(_run)


def _heartbeat_loop(
    ctx: _Context, stop_event: threading.Event, interval: int = 60
) -> None:
    """Print which examples are still in-flight every `interval` seconds.

    Runs as a daemon thread for the lifetime of phases 1-3 so a long but
    healthy run doesn't look identical to a stuck one from the terminal.
    """
    start = time.time()
    while not stop_event.wait(interval):
        with ctx.running_lock:
            names = sorted(ctx.running)
        if names:
            elapsed = int(time.time() - start)
            print(f"  ... still running after {elapsed}s: {', '.join(names)}")


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


def _fold_kfp_failures_into_results(
    results: dict[str, Result],
    poll_results: dict[str, str],
    poll_errors: dict[str, str],
    run_id_to_name: dict[str, str],
) -> None:
    """Mark an example FAIL if its KFP run didn't succeed.

    Submitting a pipeline (Phase 2) can return PASS while the run itself
    later fails, errors, or times out (Phase 4 polling) — without this, that
    failure is only visible in the printed report and `run_all()`'s exit
    code stays 0.
    """
    for run_id, status in poll_results.items():
        if status.upper() in ("SUCCEEDED", "SKIPPED"):
            continue
        name = run_id_to_name.get(run_id)
        if name not in results:
            continue
        r = results[name]
        r.status = "FAIL"
        detail = f"KFP run {run_id[:8]}...: {status}"
        err = poll_errors.get(run_id, "")
        if err:
            detail += f"\n{err}"
        r.error = f"{r.error}\n{detail}" if r.error else detail


def _print_report(
    results: dict[str, Result],
    poll_results: dict[str, str],
    poll_errors: dict[str, str],
    run_id_to_name: dict[str, str],
) -> None:
    col = 50
    passed = sum(1 for r in results.values() if r.status != "FAIL")
    failed = sum(1 for r in results.values() if r.status == "FAIL")
    skipped = [r for r in results.values() if r.status == "SKIP" and r.error]

    if skipped:
        print("\nSkipped details:")
        print("-" * 70)
        for r in skipped:
            print(f"\n{r.name}:")
            for line in r.error.splitlines():
                print(f"  {line}")

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
        if ex.api_key_dependent:
            label += "  (api-key)"
        if ex.env_mutating:
            label += "  (env-mutating, runs first in its phase)"
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
            "mlflow-credentials secret not found — run the interactive "
            "credential setup cell first"
        )
    try:
        data = _json.loads(r.stdout)["data"]
        uri = _b64.b64decode(data["MLFLOW_TRACKING_URI"]).decode().rstrip("/")
        username = _b64.b64decode(data["MLFLOW_TRACKING_USERNAME"]).decode()
        password = _b64.b64decode(data["MLFLOW_TRACKING_PASSWORD"]).decode()
    except KeyError as exc:
        return (
            False,
            f"mlflow-credentials secret is missing key {exc} — re-run the "
            "interactive credential setup cell",
        )

    if not re.match(r"^https?://", uri):
        return (
            False,
            f"mlflow-credentials secret has a malformed MLFLOW_TRACKING_URI "
            f"({uri!r}) — re-run the interactive credential setup cell and "
            "enter the full https://<domain>/mlflow URL",
        )

    creds = _b64.b64encode(f"{username}:{password}".encode()).decode()
    try:
        req = urllib.request.Request(
            f"{uri}/api/2.0/mlflow/experiments/search?max_results=1",
            headers={"Authorization": f"Basic {creds}"},
        )
        urllib.request.urlopen(req, timeout=8)
        return True, "OK"
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return False, (
                "MLflow credentials are invalid or the PAT has expired — "
                "re-run the interactive credential setup cell"
            )
        return (
            False,
            f"MLflow API returned HTTP {exc.code} — check MLFLOW_TRACKING_URI in the secret",
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"Could not reach MLflow at {uri}: {exc}"


def _check_kserve_api_key() -> tuple[bool, str]:
    """Check that headless CI has an inference API key."""
    if os.environ.get("INFERENCE_SERVICE_API_KEY", "").strip():
        return True, "OK"
    return False, (
        "INFERENCE_SERVICE_API_KEY is unset — export a model-serving API key "
        "(ask your cluster admin, or use pkui if available) before running CI"
    )


def _check_credentials() -> tuple[bool, str, bool, str]:
    """Run the MLflow and kserve API key checks, printing their outcome.

    Returns (mlflow_ok, mlflow_reason, api_key_ok, api_key_reason). Shared by
    `_preflight` (real runs) and `--dry-run` so contributors can see what
    would be skipped before committing to a full run.
    """
    print("Pre-flight: checking MLflow credentials...")
    mlflow_ok, mlflow_reason = _check_mlflow_credentials()
    if mlflow_ok:
        print("  [OK] MLflow credentials valid")
    else:
        print(f"  [SKIP] {mlflow_reason}")

    print("Pre-flight: checking kserve API key...")
    api_key_ok, api_key_reason = _check_kserve_api_key()
    if api_key_ok:
        print("  [OK] INFERENCE_SERVICE_API_KEY is set")
    else:
        print(f"  [SKIP] {api_key_reason}")

    return mlflow_ok, mlflow_reason, api_key_ok, api_key_reason


def _preflight(results: dict[str, Result]) -> bool:
    """Validate CI dependencies, MLflow credentials, and the kserve API key.

    MLflow-dependent and API-key-dependent examples are recorded as SKIP in
    `results` on failure. Returns True if MLflow credentials are valid.
    """
    _require_ci_dependencies()
    _ensure_pk_helpers()

    mlflow_ok, mlflow_reason, api_key_ok, api_key_reason = _check_credentials()

    if not mlflow_ok:
        for ex in _EXAMPLES:
            if ex.mlflow_dependent:
                results[ex.name] = Result(
                    name=ex.name, status="SKIP", error=mlflow_reason
                )

    if not api_key_ok:
        for ex in _EXAMPLES:
            if ex.api_key_dependent and ex.name not in results:
                results[ex.name] = Result(
                    name=ex.name, status="SKIP", error=api_key_reason
                )

    return mlflow_ok


# ── Phases ────────────────────────────────────────────────────────────────────


def _run_phase(
    ctx: _Context,
    phase: int,
    opts: dict[str, bool],
    predicate: Callable[[Example], bool] | None = None,
) -> dict[str, Future]:
    """Submit all examples for a given phase; return {name: Future}.

    If `predicate` is given, only examples for which it returns True are
    submitted (used to run env_mutating examples in their own sub-step).
    """
    futures: dict[str, Future] = {}
    for ex in _EXAMPLES:
        if ex.phase != phase:
            continue
        if predicate is not None and not predicate(ex):
            continue
        if ex.name in ctx.results:  # already SKIP from pre-flight
            print(f"  [SKIP  ] {ex.name}")
            continue
        if ex.opt_in and not opts.get(ex.opt_in, False):
            _skip(
                ctx, ex.name, f"opt-in: pass --{ex.opt_in.replace('_', '-')} to enable"
            )
            continue
        work = _make_work(
            ex.steps,
            ctx.root,
            ctx.output_dir,
            ctx.timeout_notebook,
            ctx.cancel_event,
        )
        futures[ex.name] = _timed_run(ctx, ex.name, work)
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
        try:
            state, err = _poll_kfp_run(
                run_id, ctx.timeout_pipeline, ctx.cancel_event
            )
        except _CancellationRequested:
            raise
        except Exception as exc:  # noqa: BLE001
            state, err = f"POLL_ERROR: {exc}", ""
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
        run_id: ctx.executor.submit(
            _poll_kfp_run, run_id, ctx.timeout_pipeline, ctx.cancel_event
        )
        for run_id in all_run_ids
    }
    for run_id, f in poll_futures.items():
        try:
            ctx.poll_results[run_id], ctx.poll_errors[run_id] = f.result()
        except _CancellationRequested:
            raise
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
    max_workers: int = 8,
) -> dict[str, Result]:
    root = _REPO_ROOT
    results: dict[str, Result] = {}

    if dry_run:
        _check_credentials()
        print()
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
    cancel_event = threading.Event()

    # SIGTERM (pkill, a dropped kubectl exec session, pod eviction) otherwise
    # kills the process immediately with no cleanup: cancel_event never gets
    # set and every _run_process child (its own session/process group) is
    # orphaned. Route it through the same cancel + cleanup path as Ctrl-C.
    def _on_sigterm(signum: int, frame: object) -> None:
        raise KeyboardInterrupt

    _old_sigterm_handler = signal.signal(signal.SIGTERM, _on_sigterm)

    executor = ThreadPoolExecutor(max_workers=max_workers)
    heartbeat_stop = threading.Event()
    try:
        try:
            ctx = _Context(
                executor=executor,
                root=root,
                output_dir=root / "ci" / "output",
                timeout_notebook=timeout_notebook,
                timeout_pipeline=timeout_pipeline,
                results=results,
                poll_results=poll_results,
                poll_errors=poll_errors,
                cancel_event=cancel_event,
            )
            threading.Thread(
                target=_heartbeat_loop, args=(ctx, heartbeat_stop), daemon=True
            ).start()

            print(
                "Phase 1a: running environment-mutating examples "
                "(pip install into the shared kernel env) sequentially first..."
            )
            _drain(ctx, _run_phase(ctx, 1, opts, predicate=lambda ex: ex.env_mutating))

            print("Phase 1: running independent examples in parallel...")
            _drain(
                ctx,
                _run_phase(ctx, 1, opts, predicate=lambda ex: not ex.env_mutating),
            )

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
        except KeyboardInterrupt:
            cancel_event.set()
            print("\nInterrupted — stopping active work before cleanup...")
            raise
        except BaseException:
            cancel_event.set()
            raise
    finally:
        signal.signal(signal.SIGTERM, _old_sigterm_handler)
        heartbeat_stop.set()
        executor.shutdown(wait=True, cancel_futures=cancel_event.is_set())
        _phase5_cleanup(cleanup_scripts)

    run_id_to_name = {
        run_id: r.name for r in results.values() for run_id in r.kfp_run_ids
    }
    _fold_kfp_failures_into_results(results, poll_results, poll_errors, run_id_to_name)
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
        help=(
            "Per-cell timeout for notebooks and whole-process timeout for scripts, "
            "in seconds (default: 1800)"
        ),
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
    parser.add_argument(
        "--max-workers",
        type=int,
        default=8,
        help=(
            "Max examples run concurrently (default: 8). Lower this if the "
            "notebook pod is being OOM-killed by running too many examples "
            "at once."
        ),
    )
    args = parser.parse_args()

    results = run_all(
        timeout_notebook=args.timeout_notebook,
        timeout_pipeline=args.timeout_pipeline,
        include_keda=args.include_keda,
        include_shadow=args.include_shadow,
        include_pytorch=args.include_pytorch,
        dry_run=args.dry_run,
        max_workers=args.max_workers,
    )

    failed = sum(1 for r in results.values() if r.status == "FAIL")
    sys.exit(1 if failed else 0)
