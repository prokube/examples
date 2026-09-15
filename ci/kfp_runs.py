"""Poll KFP runs to a terminal state and surface failed-task logs."""

from __future__ import annotations

import subprocess
import threading
import time

from .process import CancellationRequested

KFP_TERMINAL_STATES = {"SUCCEEDED", "FAILED", "ERROR", "CANCELED", "SKIPPED"}


def get_failed_task_logs(run: object, namespace: str) -> str:
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


def poll_kfp_run(
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
            raise CancellationRequested()
        run = client.get_run(run_id)
        if cancel_event.is_set():
            raise CancellationRequested()
        state = str(
            getattr(run, "state", None)
            or getattr(getattr(run, "run", None), "status", None)
            or "UNKNOWN"
        ).upper()
        if state in KFP_TERMINAL_STATES:
            error_detail = ""
            if state not in ("SUCCEEDED", "SKIPPED"):
                err = getattr(run, "error", None)
                error_detail = (getattr(err, "message", "") or "") if err else ""
                if not error_detail and namespace:
                    error_detail = get_failed_task_logs(run, namespace)
            return state, error_detail
        remaining = deadline - time.monotonic()
        if remaining > 0 and cancel_event.wait(min(interval, remaining)):
            raise CancellationRequested()
    return f"TIMEOUT after {timeout}s", ""
