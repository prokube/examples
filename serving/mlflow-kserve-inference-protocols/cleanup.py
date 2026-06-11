"""
Cleanup script for the mlflow-kserve-inference-protocols example.

Deletes (idempotently):
  - InferenceService ``v1-mobile-price-classification-inference``
  - InferenceService ``v2-mobile-price-classification-inference``

Usage
-----
    python cleanup.py [--dry-run]
"""

from __future__ import annotations

import argparse
import subprocess
import sys

_ISVC_NAMES = [
    "v1-mobile-price-classification-inference",
    "v2-mobile-price-classification-inference",
]


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
    for name in _ISVC_NAMES:
        _kubectl_delete("inferenceservice", name, "-n", ns, dry_run=dry_run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print commands without executing them"
    )
    args = parser.parse_args()
    cleanup(dry_run=args.dry_run)
