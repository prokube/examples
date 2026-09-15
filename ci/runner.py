"""Phase orchestration: submit examples, poll KFP runs, and always clean up."""

from __future__ import annotations

import signal
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .kfp_runs import poll_kfp_run
from .notebook import (
    extract_run_ids_from_notebook,
    extract_run_ids_from_stdout,
    run_notebook,
)
from .preflight import check_credentials, preflight
from .process import CancellationRequested, run_cleanup, run_script
from .registry import EXAMPLES, EXTRA_CLEANUP_PATHS, REPO_ROOT, Example, Step
from .results import (
    Result,
    fold_kfp_failures_into_results,
    print_dry_run,
    print_report,
    print_result,
)


# ── Orchestration context ─────────────────────────────────────────────────────


@dataclass
class Context:
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


def make_work(
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
                raise CancellationRequested()
            if step.kind == "notebook":
                out = run_notebook(
                    root / step.path, output_dir, timeout, root, cancel_event
                )
                if step.extract_run_ids:
                    result.kfp_run_ids.extend(extract_run_ids_from_notebook(out))
            elif step.kind == "script":
                stdout, _ = run_script(
                    root / step.path,
                    timeout,
                    cancel_event,
                    extra_args=step.extra_args or None,
                )
                if step.extract_run_ids:
                    result.kfp_run_ids.extend(extract_run_ids_from_stdout(stdout))

    return work


def timed_run(
    ctx: Context,
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
        except CancellationRequested:
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


def heartbeat_loop(
    ctx: Context, stop_event: threading.Event, interval: int = 60
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


def drain(ctx: Context, futures: dict[str, Future]) -> None:
    """Wait on a {name: Future} map, printing each result as it completes."""
    by_future = {v: k for k, v in futures.items()}
    for f in as_completed(futures.values()):
        print_result(ctx.results[by_future[f]])


def skip(ctx: Context, name: str, reason: str) -> None:
    """Record a SKIP result and print a one-line notice."""
    print(f"  [SKIP  ] {name}")
    ctx.results[name] = Result(name=name, status="SKIP", error=reason)


# ── Phases ────────────────────────────────────────────────────────────────────


def run_phase(
    ctx: Context,
    phase: int,
    opts: dict[str, bool],
    predicate: Callable[[Example], bool] | None = None,
) -> dict[str, Future]:
    """Submit all examples for a given phase; return {name: Future}.

    If `predicate` is given, only examples for which it returns True are
    submitted (used to run env_mutating examples in their own sub-step).
    """
    futures: dict[str, Future] = {}
    for ex in EXAMPLES:
        if ex.phase != phase:
            continue
        if predicate is not None and not predicate(ex):
            continue
        if ex.name in ctx.results:  # already SKIP from pre-flight
            print(f"  [SKIP  ] {ex.name}")
            continue
        if ex.opt_in and not opts.get(ex.opt_in, False):
            skip(
                ctx, ex.name, f"opt-in: pass --{ex.opt_in.replace('_', '-')} to enable"
            )
            continue
        work = make_work(
            ex.steps,
            ctx.root,
            ctx.output_dir,
            ctx.timeout_notebook,
            ctx.cancel_event,
        )
        futures[ex.name] = timed_run(ctx, ex.name, work)
    return futures


def await_mobile_price(ctx: Context, phase2_futures: dict[str, Future]) -> bool:
    """Wait for mlflow-mobile-price and poll its KFP run inline.

    Phase 3 ISVCs need the registered model, so this must complete before
    Phase 3 starts. Returns True if the model is registered and ready.
    """
    name = "mlflow/mobile-price-classification"
    if name not in phase2_futures:
        return False

    phase2_futures[name].result()
    print_result(ctx.results[name])
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
            state, err = poll_kfp_run(run_id, ctx.timeout_pipeline, ctx.cancel_event)
        except CancellationRequested:
            raise
        except Exception as exc:  # noqa: BLE001
            state, err = f"POLL_ERROR: {exc}", ""
        ctx.poll_results[run_id] = state
        ctx.poll_errors[run_id] = err
        print(f"    [{state}] {run_id[:8]}...")
        if state.upper() != "SUCCEEDED":
            ok = False
    return ok


def phase4_poll(ctx: Context) -> None:
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
            poll_kfp_run, run_id, ctx.timeout_pipeline, ctx.cancel_event
        )
        for run_id in all_run_ids
    }
    for run_id, f in poll_futures.items():
        try:
            ctx.poll_results[run_id], ctx.poll_errors[run_id] = f.result()
        except CancellationRequested:
            raise
        except Exception as exc:  # noqa: BLE001
            ctx.poll_results[run_id] = f"POLL_ERROR: {exc}"
            ctx.poll_errors[run_id] = ""
        print(f"  [{ctx.poll_results[run_id]}] {run_id[:8]}...")


def phase5_cleanup(cleanup_scripts: list[Path]) -> None:
    print("\nPhase 5: running cleanup scripts...")
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(run_cleanup, p) for p in cleanup_scripts if p.exists()]
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
    root = REPO_ROOT
    results: dict[str, Result] = {}

    if dry_run:
        check_credentials()
        print()
        print_dry_run()
        return results

    preflight(results)

    opts = {
        "include_keda": include_keda,
        "include_pytorch": include_pytorch,
        "include_shadow": include_shadow,
    }
    cleanup_scripts = [root / ex.cleanup for ex in EXAMPLES if ex.cleanup] + [
        root / p for p in EXTRA_CLEANUP_PATHS
    ]
    poll_results: dict[str, str] = {}
    poll_errors: dict[str, str] = {}
    cancel_event = threading.Event()

    # SIGTERM (pkill, a dropped kubectl exec session, pod eviction) otherwise
    # kills the process immediately with no cleanup: cancel_event never gets
    # set and every run_process child (its own session/process group) is
    # orphaned. Route it through the same cancel + cleanup path as Ctrl-C.
    def _on_sigterm(signum: int, frame: object) -> None:
        raise KeyboardInterrupt

    _old_sigterm_handler = signal.signal(signal.SIGTERM, _on_sigterm)

    executor = ThreadPoolExecutor(max_workers=max_workers)
    heartbeat_stop = threading.Event()
    try:
        try:
            ctx = Context(
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
                target=heartbeat_loop, args=(ctx, heartbeat_stop), daemon=True
            ).start()

            print(
                "Phase 1a: running environment-mutating examples "
                "(pip install into the shared kernel env) sequentially first..."
            )
            drain(ctx, run_phase(ctx, 1, opts, predicate=lambda ex: ex.env_mutating))

            print("Phase 1: running independent examples in parallel...")
            drain(
                ctx,
                run_phase(ctx, 1, opts, predicate=lambda ex: not ex.env_mutating),
            )

            print("\nPhase 2: submitting pipelines...")
            phase2_futures = run_phase(ctx, 2, opts)
            mobile_price_ok = await_mobile_price(ctx, phase2_futures)

            print("\nPhase 3: deploying MLflow KServe InferenceServices...")
            if mobile_price_ok:
                phase3_futures = run_phase(ctx, 3, opts)
            else:
                skipped = "mlflow/mobile-price-classification" not in phase2_futures
                reason = (
                    "prerequisite mlflow/mobile-price-classification skipped (MLflow credentials)"
                    if skipped
                    else "prerequisite mlflow/mobile-price-classification notebook or KFP pipeline did not succeed"
                )
                print(f"  [SKIP] {reason}")
                for ex in EXAMPLES:
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
            drain(ctx, remaining)

            phase4_poll(ctx)
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
        phase5_cleanup(cleanup_scripts)

    run_id_to_name = {
        run_id: r.name for r in results.values() for run_id in r.kfp_run_ids
    }
    fold_kfp_failures_into_results(results, poll_results, poll_errors, run_id_to_name)
    print_report(results, poll_results, poll_errors, run_id_to_name)
    return results
