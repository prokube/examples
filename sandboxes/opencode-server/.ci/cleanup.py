"""Delete the opencode sandbox."""

from __future__ import annotations

import argparse
import sys

from prokube.sandbox import SandboxClient

_SANDBOX = "opencode"


def cleanup(dry_run: bool = False) -> None:
    if dry_run:
        print(f"[dry-run] delete sandbox {_SANDBOX}")
        return
    with SandboxClient() as sandboxes:
        try:
            sandboxes.delete(_SANDBOX)
            print(f"deleted sandbox {_SANDBOX}")
        except Exception as error:  # e.g. NotFoundError
            print(f"WARNING: {error}", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print commands without executing"
    )
    args = parser.parse_args()
    cleanup(dry_run=args.dry_run)
