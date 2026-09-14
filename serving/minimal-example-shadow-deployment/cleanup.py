"""Delete the shadow example's InferenceServices and Postgres cluster."""

from __future__ import annotations

import argparse
import subprocess
import sys


def _namespace() -> str:
    with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace") as fh:
        return fh.read().strip()


def _kubectl_delete(*args: str, dry_run: bool = False) -> None:
    # --wait=false: sequential blocking deletes of the PostgresCluster (with
    # PVCs) can exceed _run_cleanup's 120s budget and skip later deletes.
    cmd = ["kubectl", "delete", *args, "--ignore-not-found", "--wait=false"]
    if dry_run:
        print(f"[dry-run] {' '.join(cmd)}")
        return
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"WARNING: {result.stderr.strip()}", file=sys.stderr)
    else:
        print(result.stdout.strip() or f"deleted (or not found): {' '.join(args)}")


def cleanup(dry_run: bool = False) -> None:
    ns = _namespace()
    _kubectl_delete(
        "inferenceservice", "double-minimal-custom-inference", "-n", ns, dry_run=dry_run
    )
    _kubectl_delete(
        "inferenceservice", "triple-minimal-custom-inference", "-n", ns, dry_run=dry_run
    )
    _kubectl_delete(
        "postgrescluster", "inferencing-postgres", "-n", ns, dry_run=dry_run
    )
    # Can be left behind if apply.py was killed mid-run despite --rm.
    _kubectl_delete("pod", "pg-schema-init", "-n", ns, dry_run=dry_run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print commands without executing"
    )
    args = parser.parse_args()
    cleanup(dry_run=args.dry_run)
