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
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── Repo root ─────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(
    subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
)

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


def _run_notebook(nb_path: Path, output_dir: Path, timeout: int) -> tuple[Path, str]:
    """Execute a notebook with papermill. Returns (output_path, stderr)."""
    try:
        import papermill as pm
    except ImportError:
        raise RuntimeError("papermill is not installed. Run: pip install papermill")

    output_path = output_dir / nb_path.name
    output_dir.mkdir(parents=True, exist_ok=True)
    pm.execute_notebook(
        str(nb_path),
        str(output_path),
        kernel_name="python3",
        execution_timeout=timeout,
        cwd=str(nb_path.parent),
    )
    return output_path, ""


def _run_script(script_path: Path, timeout: int) -> tuple[str, str]:
    """Run a plain Python script. Returns (stdout, stderr)."""
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(script_path.parent),
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
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


def _poll_kfp_run(run_id: str, timeout: int, interval: int = 30) -> str:
    """Poll a KFP run until terminal state. Returns final status string."""
    try:
        from kfp.client import Client
    except ImportError:
        return "SKIP (kfp not installed)"
    client = Client()
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get_run(run_id)
        state = run.run.status
        if state in ("Succeeded", "Failed", "Error", "Skipped"):
            return state
        time.sleep(interval)
    return f"TIMEOUT after {timeout}s"


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

    def _run():
        t0 = time.time()
        try:
            out, _ = _run_notebook(nb_path, output_dir, timeout)
            result.status = "PASS"
            result.kfp_run_ids = _extract_run_ids_from_notebook(out)
        except Exception as exc:  # noqa: BLE001
            result.status = "FAIL"
            result.error = str(exc)[:300]
        finally:
            result.duration = time.time() - t0

    return executor.submit(_run)


def _submit_script(
    executor: ThreadPoolExecutor,
    results: dict[str, Result],
    name: str,
    script_path: Path,
    timeout: int,
) -> Future:
    result = Result(name=name)
    results[name] = result

    def _run():
        t0 = time.time()
        try:
            stdout, _ = _run_script(script_path, timeout)
            result.status = "PASS"
            result.kfp_run_ids = _extract_run_ids_from_stdout(stdout)
        except Exception as exc:  # noqa: BLE001
            result.status = "FAIL"
            result.error = str(exc)[:300]
        finally:
            result.duration = time.time() - t0

    return executor.submit(_run)


# ── Report ────────────────────────────────────────────────────────────────────


def _print_report(results: dict[str, Result], poll_results: dict[str, str]) -> None:
    col = 50
    print("\n" + "=" * 70)
    print(f"{'EXAMPLE':<{col}} {'STATUS':<10} {'DURATION'}")
    print("-" * 70)
    passed = failed = 0
    for r in results.values():
        dur = f"{r.duration:.0f}s" if r.duration else "-"
        print(f"{r.name:<{col}} {r.status:<10} {dur}")
        if r.status == "FAIL":
            print(f"  {'':>{col}}  {r.error}")
            failed += 1
        else:
            passed += 1
    if poll_results:
        print()
        print(f"{'KFP PIPELINE POLL':<{col}} {'STATUS':<10}")
        print("-" * 70)
        for run_id, status in poll_results.items():
            short = run_id[:8] + "..."
            ok = status == "Succeeded"
            if not ok:
                failed += 1
            else:
                passed += 1
            print(f"{short:<{col}} {status:<10}")
    print("=" * 70)
    print(f"PASSED: {passed}   FAILED: {failed}   TOTAL: {passed + failed}")
    print()


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
                ("mlflow/mlflow-quickstart", "mlflow/mlflow-quickstart-example.ipynb"),
                ("mlflow/mlflow-image-example", "mlflow/mlflow-image-example.ipynb"),
                ("mlflow/mlflow-kfp-example", "mlflow/mlflow-kfp-example.ipynb"),
                (
                    "serving/minimal-s3-model",
                    "serving/minimal-s3-model/minimal-s3-model.ipynb",
                ),
            ]:
                f = _submit_notebook(
                    executor, results, name, root / rel, output_dir, timeout_notebook
                )
                phase1_futures[name] = f

            # wait for all phase 1
            for name, f in phase1_futures.items():
                f.result()
                print(f"  [{results[name].status}] {name}")

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

            # Wait only for mlflow-mobile-price before launching phase 3
            mlflow_mobile_future = phase2_futures["mlflow/mobile-price-classification"]
            mlflow_mobile_future.result()
            print(
                f"  [{results['mlflow/mobile-price-classification'].status}] mlflow/mobile-price-classification"
            )

            # ── Phase 3: MLflow KServe examples (need registered model) ───────
            print("\nPhase 3: deploying MLflow KServe InferenceServices...")
            phase3_futures = {}
            for name, rel in [
                (
                    "serving/mlflow-kserve-minimal",
                    "serving/mlflow-kserve-minimal/apply.py",
                ),
                (
                    "serving/mlflow-kserve-inference-protocols",
                    "serving/mlflow-kserve-inference-protocols/inference_protocol_version_example.ipynb",
                ),
            ]:
                path = root / rel
                if path.suffix == ".ipynb":
                    f = _submit_notebook(
                        executor, results, name, path, output_dir, timeout_notebook
                    )
                else:
                    f = _submit_script(executor, results, name, path, timeout_notebook)
                phase3_futures[name] = f

            # Wait for remaining phase 2 futures while phase 3 runs
            for name, f in phase2_futures.items():
                if name != "mlflow/mobile-price-classification":
                    f.result()
                    print(f"  [{results[name].status}] {name}")

            # Wait for phase 3
            for name, f in phase3_futures.items():
                f.result()
                print(f"  [{results[name].status}] {name}")

            # ── Phase 4: KFP run polling ──────────────────────────────────────
            all_run_ids: list[str] = []
            for r in results.values():
                all_run_ids.extend(r.kfp_run_ids)

            if all_run_ids:
                print(f"\nPhase 4: polling {len(all_run_ids)} KFP run(s)...")
                poll_futures = {
                    run_id: executor.submit(_poll_kfp_run, run_id, timeout_pipeline)
                    for run_id in all_run_ids
                }
                for run_id, f in poll_futures.items():
                    poll_results[run_id] = f.result()
                    print(f"  [{poll_results[run_id]}] {run_id[:8]}...")
            else:
                print("\nPhase 4: no KFP run IDs found, skipping poll.")

    finally:
        # ── Phase 5: cleanup ─────────────────────────────────────────────────
        print("\nPhase 5: running cleanup scripts...")
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = [ex.submit(_run_cleanup, p) for p in cleanup_scripts if p.exists()]
            for f in as_completed(futs):
                f.result()  # already swallows exceptions inside _run_cleanup

    _print_report(results, poll_results)
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
