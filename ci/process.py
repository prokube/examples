"""Cancellable subprocess execution: scripts and cleanup.py runners."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path


class CancellationRequested(Exception):
    pass


def stop_process(proc: subprocess.Popen[str]) -> tuple[str, str]:
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


def run_process(
    cmd: list[str],
    cwd: Path,
    cancel_event: threading.Event,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a cancellable process and reap its process group before returning."""
    if cancel_event.is_set():
        raise CancellationRequested()
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
            stop_process(proc)
            raise CancellationRequested()
        if deadline is not None and time.monotonic() >= deadline:
            stdout, stderr = stop_process(proc)
            detail = (stderr or stdout or "(no output)").strip()
            raise RuntimeError(f"Timed out after {timeout}s: {detail}")
        try:
            stdout, stderr = proc.communicate(timeout=0.5)
            return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            pass


def run_script(
    script_path: Path,
    timeout: int,
    cancel_event: threading.Event,
    extra_args: list[str] | None = None,
) -> tuple[str, str]:
    """Run a plain Python script. Returns (stdout, stderr)."""
    cmd = [sys.executable, str(script_path)] + (extra_args or [])
    result = run_process(
        cmd,
        cwd=script_path.parent,
        cancel_event=cancel_event,
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "(no output)").strip()
        raise RuntimeError(detail)
    return result.stdout, result.stderr


def run_cleanup(cleanup_path: Path) -> None:
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
