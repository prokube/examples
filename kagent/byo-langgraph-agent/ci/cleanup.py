"""Delete the LangGraph BYO agent and the Anthropic Secret."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

_EXAMPLE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MANIFESTS = ["agent.yaml", "../basic-agent/anthropic-secret.yaml"]


def _namespace() -> str:
    with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace") as fh:
        return fh.read().strip()


def cleanup(dry_run: bool = False) -> None:
    ns = _namespace()
    for manifest in _MANIFESTS:
        path = os.path.normpath(os.path.join(_EXAMPLE_DIR, manifest))
        cmd = ["kubectl", "delete", "-n", ns, "-f", path, "--ignore-not-found"]
        if dry_run:
            print(f"[dry-run] {' '.join(cmd)}")
            continue
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"WARNING: {result.stderr.strip()}", file=sys.stderr)
        else:
            print(result.stdout.strip() or f"deleted (or not found): {manifest}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print commands without executing"
    )
    args = parser.parse_args()
    cleanup(dry_run=args.dry_run)
