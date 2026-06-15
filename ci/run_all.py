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


def _submit_notebook(
    executor: ThreadPoolExecutor,
    results: dict[str, Result],
    name: str,
    nb_path: Path,
    output_dir: Path,
    timeout: int,
) -> Future:
    result = Result(name=name)
    results[name] = result
    print(f"  [START  ] {name}")

    def _run():
        t0 = time.time()
        try:
            out = _run_notebook(nb_path, output_dir, timeout)
            result.status = "PASS"
            result.kfp_run_ids = _extract_run_ids_from_notebook(out)
        except Exception as exc:  # noqa: BLE001
            result.status = "FAIL"
            result.error = str(exc)
        finally:
            result.duration = time.time() - t0

    return executor.submit(_run)


def _submit_script(
    executor: ThreadPoolExecutor,
    results: dict[str, Result],
    name: str,
    script_path: Path,
    timeout: int,
    extra_args: list[str] | None = None,
) -> Future:
    result = Result(name=name)
    results[name] = result
    print(f"  [START  ] {name}")

    def _run():
        t0 = time.time()
        try:
            stdout, _ = _run_script(script_path, timeout, extra_args=extra_args)
            result.status = "PASS"
            result.kfp_run_ids = _extract_run_ids_from_stdout(stdout)
        except Exception as exc:  # noqa: BLE001
            result.status = "FAIL"
            result.error = str(exc)
        finally:
            result.duration = time.time() - t0

    return executor.submit(_run)


def _submit_chain(
    executor: ThreadPoolExecutor,
    results: dict[str, Result],
    name: str,
    steps: list[tuple[str, Path, dict]],
    output_dir: Path,
    timeout: int,
) -> Future:
    """Submit a sequential chain of (kind, path, kwargs) steps as a single named result.

    kind is 'notebook' or 'script'.  kwargs may include 'extra_args' for scripts.
    All steps run in one thread; the first failure stops the chain.
    """
    result = Result(name=name)
    results[name] = result
    print(f"  [START  ] {name}")

    def _run():
        t0 = time.time()
        try:
            for kind, path, kwargs in steps:
                if kind == "notebook":
                    out = _run_notebook(path, output_dir, timeout)
                    result.kfp_run_ids.extend(_extract_run_ids_from_notebook(out))
                elif kind == "script":
                    stdout, _ = _run_script(
                        path, timeout, extra_args=kwargs.get("extra_args")
                    )
                    result.kfp_run_ids.extend(_extract_run_ids_from_stdout(stdout))
            result.status = "PASS"
        except Exception as exc:  # noqa: BLE001
            result.status = "FAIL"
            result.error = str(exc)
        finally:
            result.duration = time.time() - t0

    return executor.submit(_run)


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


# ── Main ──────────────────────────────────────────────────────────────────────


def run_all(
    timeout_notebook: int = 1800,
    timeout_pipeline: int = 3600,
    include_keda: bool = False,
    dry_run: bool = False,
) -> dict[str, Result]:
    root = _REPO_ROOT
    output_dir = root / "ci" / "output"
    results: dict[str, Result] = {}
    poll_results: dict[str, str] = {}
    poll_errors: dict[str, str] = {}

    _ensure_papermill()

    # Pre-flight: validate MLflow credentials; skip dependent tests if unavailable
    print("Pre-flight: checking MLflow credentials...")
    mlflow_ok, mlflow_reason = _check_mlflow_credentials()
    if mlflow_ok:
        print("  [OK] MLflow credentials valid")
    else:
        print(f"  [SKIP] {mlflow_reason}")
        for name in _MLFLOW_DEPENDENT:
            results[name] = Result(name=name, status="SKIP", error=mlflow_reason)

    if dry_run:
        print("[dry-run] Would execute the following phases:")
        for label in [
            "Phase 1: dask, mlflow-quickstart, mlflow-image, mlflow-kfp, minimal-s3-model",
            "Phase 2: mlflow-mobile-price, lightweight-components, lightweight-python-package",
            "Phase 3: mlflow-kserve-minimal, mlflow-kserve-inference-protocols",
            "Phase 4: KFP run polling",
            "Phase 5: cleanup",
        ]:
            print(f"  {label}")
        return results

    cleanup_scripts = [
        root / "notebooks" / "dask" / "cleanup.py",
        root / "serving" / "minimal-s3-model" / "cleanup.py",
        root / "serving" / "mlflow-kserve-minimal" / "cleanup.py",
        root / "serving" / "mlflow-kserve-inference-protocols" / "cleanup.py",
        root / "hparam-tuning" / "minimal-mnist" / "cleanup.py",
    ]

    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            # ── Phase 1: independent notebooks ───────────────────────────────
            print("Phase 1: running independent notebooks in parallel...")
            phase1_futures = {}
            for name, rel in [
                ("notebooks/dask", "notebooks/dask/dask_example.ipynb"),
                (
                    "notebooks/mobile-price-classification",
                    "notebooks/mobile-price-classification/mobile-price-classifications.ipynb",
                ),
                ("mlflow/mlflow-quickstart", "mlflow/mlflow-quickstart-example.ipynb"),
                ("mlflow/mlflow-image-example", "mlflow/mlflow-image-example.ipynb"),
                ("mlflow/mlflow-kfp-example", "mlflow/mlflow-kfp-example.ipynb"),
                (
                    "serving/minimal-s3-model",
                    "serving/minimal-s3-model/minimal-s3-model.ipynb",
                ),
            ]:
                if name in results:  # already SKIP from pre-flight
                    print(f"  [SKIP  ] {name}")
                    continue
                f = _submit_notebook(
                    executor, results, name, root / rel, output_dir, timeout_notebook
                )
                phase1_futures[name] = f

            # mnist-vae: training script (reduced epochs) → visualization notebook
            # run as a sequential chain in a single thread, parallel to other Phase 1
            phase1_futures["notebooks/mnist-vae"] = _submit_chain(
                executor,
                results,
                "notebooks/mnist-vae",
                steps=[
                    (
                        "script",
                        root / "notebooks/mnist-vae/run_training.py",
                        {"extra_args": ["--max_epochs", "3"]},
                    ),
                    ("notebook", root / "notebooks/mnist-vae/visualizations.ipynb", {}),
                ],
                output_dir=output_dir,
                timeout=timeout_notebook,
            )

            # wait for all phase 1, printing results as each finishes
            _future_to_name = {v: k for k, v in phase1_futures.items()}
            for f in as_completed(phase1_futures.values()):
                _print_result(results[_future_to_name[f]])

            # ── Phase 2: pipeline submissions (return fast) ───────────────────
            print("\nPhase 2: submitting pipelines...")
            phase2_futures = {}
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
                if name in results:  # already SKIP from pre-flight
                    print(f"  [SKIP  ] {name}")
                    continue
                f = _submit_notebook(
                    executor, results, name, root / rel, output_dir, timeout_notebook
                )
                phase2_futures[name] = f

            lpp_future = _submit_script(
                executor,
                results,
                "pipelines/lightweight-python-package",
                root / "pipelines" / "lightweight-python-package" / "submit-cluster.py",
                timeout_notebook,
            )
            phase2_futures["pipelines/lightweight-python-package"] = lpp_future

            mcc_future = _submit_script(
                executor,
                results,
                "pipelines/minimal-container-components",
                root
                / "pipelines"
                / "minimal-container-components"
                / "submit-cluster.py",
                timeout_notebook,
            )
            phase2_futures["pipelines/minimal-container-components"] = mcc_future

            # Wait for mlflow-mobile-price notebook; then poll its KFP run
            # inline before Phase 3 — the ISVC needs the registered model.
            _mobile_price_skipped = (
                "mlflow/mobile-price-classification" not in phase2_futures
            )
            if not _mobile_price_skipped:
                phase2_futures["mlflow/mobile-price-classification"].result()
                _print_result(results["mlflow/mobile-price-classification"])

            _mobile_price_ok = (
                not _mobile_price_skipped
                and results["mlflow/mobile-price-classification"].status == "PASS"
            )

            if _mobile_price_ok:
                _mobile_run_ids = results[
                    "mlflow/mobile-price-classification"
                ].kfp_run_ids
                if _mobile_run_ids:
                    print(
                        "  Polling mlflow-mobile-price KFP pipeline (model must be registered before ISVCs)..."
                    )
                    for _run_id in _mobile_run_ids:
                        _state, _err = _poll_kfp_run(_run_id, timeout_pipeline)
                        poll_results[_run_id] = (
                            _state  # recorded here; Phase 4 will skip it
                        )
                        poll_errors[_run_id] = _err
                        print(f"    [{_state}] {_run_id[:8]}...")
                        if _state.upper() != "SUCCEEDED":
                            _mobile_price_ok = False

            # ── Phase 3: MLflow KServe examples (need registered model) ───────
            print("\nPhase 3: deploying MLflow KServe InferenceServices...")
            if not _mobile_price_ok:
                _reason = (
                    "prerequisite mlflow/mobile-price-classification skipped (MLflow credentials)"
                    if _mobile_price_skipped
                    else "prerequisite mlflow/mobile-price-classification notebook or KFP pipeline did not succeed"
                )
                print(f"  [SKIP] {_reason}")
                for name in (
                    "serving/mlflow-kserve-minimal",
                    "serving/mlflow-kserve-inference-protocols",
                ):
                    results[name] = Result(name=name, status="SKIP", error=_reason)
                phase3_futures = {}
            else:
                phase3_futures = {}

                # mlflow-kserve-minimal: deploy then immediately smoke-test
                # deploy_and_test() in apply.py handles both steps
                phase3_futures["serving/mlflow-kserve-minimal"] = _submit_script(
                    executor,
                    results,
                    "serving/mlflow-kserve-minimal",
                    root / "serving" / "mlflow-kserve-minimal" / "apply.py",
                    timeout_notebook,
                )

                # inference-protocols notebook handles its own deploy + test
                phase3_futures["serving/mlflow-kserve-inference-protocols"] = (
                    _submit_notebook(
                        executor,
                        results,
                        "serving/mlflow-kserve-inference-protocols",
                        root
                        / "serving/mlflow-kserve-inference-protocols/inference_protocol_version_example.ipynb",
                        output_dir,
                        timeout_notebook,
                    )
                )

            # Phase 2 remaining + phase 3 run concurrently; print as each finishes
            print("\nPhase 2 (remaining) + Phase 3 running concurrently...")
            remaining = {
                **{
                    k: v
                    for k, v in phase2_futures.items()
                    if k != "mlflow/mobile-price-classification"
                },
                **phase3_futures,
            }
            _future_to_name2 = {v: k for k, v in remaining.items()}
            for f in as_completed(remaining.values()):
                _print_result(results[_future_to_name2[f]])

            # ── Phase 4: KFP run polling ──────────────────────────────────────
            # Exclude run IDs already polled inline before Phase 3
            all_run_ids: list[str] = [
                rid
                for r in results.values()
                for rid in r.kfp_run_ids
                if rid not in poll_results
            ]

            if all_run_ids:
                print(f"\nPhase 4: polling {len(all_run_ids)} KFP run(s)...")
                poll_futures = {
                    run_id: executor.submit(_poll_kfp_run, run_id, timeout_pipeline)
                    for run_id in all_run_ids
                }
                for run_id, f in poll_futures.items():
                    try:
                        poll_results[run_id], poll_errors[run_id] = f.result()
                    except Exception as exc:  # noqa: BLE001
                        poll_results[run_id] = f"POLL_ERROR: {exc}"
                        poll_errors[run_id] = ""
                    state = poll_results[run_id]
                    print(f"  [{state}] {run_id[:8]}...")
            else:
                print("\nPhase 4: no KFP run IDs found, skipping poll.")

    finally:
        # ── Phase 5: cleanup ─────────────────────────────────────────────────
        print("\nPhase 5: running cleanup scripts...")
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = [ex.submit(_run_cleanup, p) for p in cleanup_scripts if p.exists()]
            for f in as_completed(futs):
                f.result()  # already swallows exceptions inside _run_cleanup

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
        help="Include GPU-dependent KEDA autoscaling example (opt-in)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print plan without executing anything"
    )
    args = parser.parse_args()

    results = run_all(
        timeout_notebook=args.timeout_notebook,
        timeout_pipeline=args.timeout_pipeline,
        include_keda=args.include_keda,
        dry_run=args.dry_run,
    )

    failed = sum(1 for r in results.values() if r.status == "FAIL")
    sys.exit(1 if failed else 0)
