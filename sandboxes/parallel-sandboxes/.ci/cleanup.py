"""Delete the parallel-* sandboxes."""

from __future__ import annotations

import argparse
import sys

from prokube.sandbox import SandboxClient

_PREFIX = "sbx-parallel-"


def cleanup(dry_run: bool = False) -> None:
    with SandboxClient() as sandboxes:
        for sandbox in sandboxes.list():
            name = sandbox.metadata.name
            if not name.startswith(_PREFIX):
                continue
            if dry_run:
                print(f"[dry-run] delete sandbox {name}")
                continue
            try:
                sandboxes.delete(name)
                print(f"deleted sandbox {name}")
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
