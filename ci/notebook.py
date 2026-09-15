"""Papermill notebook execution and KFP run-ID extraction from outputs."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path

from .process import CancellationRequested

# KFP run ID pattern (UUID v4)
RUN_ID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def format_papermill_error(exc: Exception) -> str:
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


def strip_ci_skip_cells(nb_path: Path, output_dir: Path) -> Path:
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


def run_notebook(
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
        raise CancellationRequested()

    import papermill as pm
    from papermill.exceptions import PapermillExecutionError

    output_dir = output_dir / nb_path.parent.relative_to(root)
    output_dir.mkdir(parents=True, exist_ok=True)
    nb_to_run = strip_ci_skip_cells(nb_path, output_dir)
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
        raise RuntimeError(format_papermill_error(exc)) from exc
    return output_path


def extract_run_ids_from_notebook(output_nb: Path) -> list[str]:
    """Parse a papermill output notebook for KFP run IDs."""
    with open(output_nb) as fh:
        nb = json.load(fh)
    ids: list[str] = []
    for cell in nb.get("cells", []):
        for output in cell.get("outputs", []):
            text = "".join(
                output.get("text", []) + output.get("data", {}).get("text/plain", [])
            )
            ids.extend(RUN_ID_RE.findall(text))
    return list(dict.fromkeys(ids))


def extract_run_ids_from_stdout(stdout: str) -> list[str]:
    """Parse stdout from a script for KFP_RUN_ID=<uuid> lines."""
    ids = []
    for line in stdout.splitlines():
        if line.startswith("KFP_RUN_ID="):
            ids.append(line.split("=", 1)[1].strip())
    return ids
