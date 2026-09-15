"""Per-example Result record and the end-of-run / dry-run reports."""

from __future__ import annotations

from dataclasses import dataclass, field

from .registry import EXAMPLES


@dataclass
class Result:
    name: str
    status: str = "PENDING"  # PASS | FAIL | SKIP
    duration: float = 0.0
    error: str = ""
    kfp_run_ids: list[str] = field(default_factory=list)


def print_result(r: Result) -> None:
    dur = f"{r.duration:.0f}s" if r.duration else "-"
    print(f"  [{r.status}] {r.name}  ({dur})")
    if r.status == "FAIL" and r.error:
        for line in r.error.splitlines():
            print(f"         {line}")


def fold_kfp_failures_into_results(
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


def print_report(
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


def print_dry_run() -> None:
    by_phase: dict[int, list[str]] = {}
    for ex in EXAMPLES:
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
