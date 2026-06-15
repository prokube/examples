"""
Cleanup script for the minimal-example-shadow-deployment example.

Deletes (idempotently):
  - InferenceService ``double-minimal-custom-inference``
  - InferenceService ``triple-minimal-custom-inference``
  - PostgresCluster  ``inferencing-postgres``

Usage
-----
    python cleanup.py [--dry-run]
"""

from __future__ import annotations

import argparse
import subprocess
import sys


def _namespace() -> str:
    with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace") as fh:
        return fh.read().strip()


def _kubectl_delete(*args: str, dry_run: bool = False) -> None:
    cmd = ["kubectl", "delete", *args, "--ignore-not-found"]
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print commands without executing"
    )
    args = parser.parse_args()
    cleanup(dry_run=args.dry_run)
