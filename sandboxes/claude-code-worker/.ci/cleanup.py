"""Delete the claude-code sandbox and the Anthropic Secret."""

from __future__ import annotations

import argparse
import subprocess
import sys

from prokube.sandbox import SandboxClient

_SANDBOX = "claude-code"
_SECRET = "anthropic-api-key"


def _namespace() -> str:
    with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace") as fh:
        return fh.read().strip()


def cleanup(dry_run: bool = False) -> None:
    cmd = [
        "kubectl",
        "delete",
        "-n",
        _namespace(),
        "secret",
        _SECRET,
        "--ignore-not-found",
    ]
    if dry_run:
        print(f"[dry-run] delete sandbox {_SANDBOX}")
        print(f"[dry-run] {' '.join(cmd)}")
        return
    with SandboxClient() as sandboxes:
        try:
            sandboxes.delete(_SANDBOX)
            print(f"deleted sandbox {_SANDBOX}")
        except Exception as error:  # e.g. NotFoundError
            print(f"WARNING: {error}", file=sys.stderr)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"WARNING: {result.stderr.strip()}", file=sys.stderr)
    else:
        print(result.stdout.strip() or f"deleted (or not found): {_SECRET}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print commands without executing"
    )
    args = parser.parse_args()
    cleanup(dry_run=args.dry_run)
