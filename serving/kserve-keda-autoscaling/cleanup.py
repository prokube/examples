"""
Cleanup script for the kserve-keda-autoscaling example.

Deletes (idempotently, ScaledObject first to stop KEDA activity):
  - ScaledObject  ``opt-125m-scaledobject``
  - InferenceService ``opt-125m``

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
    # Delete the ScaledObject before the ISVC so KEDA stops managing the HPA
    # before the underlying Deployment is gone.
    _kubectl_delete("scaledobject", "opt-125m-scaledobject", "-n", ns, dry_run=dry_run)
    _kubectl_delete("inferenceservice", "opt-125m", "-n", ns, dry_run=dry_run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print commands without executing"
    )
    args = parser.parse_args()
    cleanup(dry_run=args.dry_run)
