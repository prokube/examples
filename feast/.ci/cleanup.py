"""Delete the Redis online store and the S3 objects created by the Feast example."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

_MANIFEST = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "redis.yaml"
)
_S3_PREFIX = "feast-example"  # must match S3_ROOT in feast_example.ipynb


def _namespace() -> str:
    with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace") as fh:
        return fh.read().strip()


def _kubectl_delete(ns: str, *args: str, dry_run: bool) -> None:
    cmd = ["kubectl", "delete", "-n", ns, *args, "--ignore-not-found"]
    if dry_run:
        print(f"[dry-run] {' '.join(cmd)}")
        return
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"WARNING: {result.stderr.strip()}", file=sys.stderr)
    else:
        print(result.stdout.strip() or f"deleted (or not found): {' '.join(args)}")


def _delete_s3_prefix(path: str, dry_run: bool) -> None:
    if dry_run:
        print(f"[dry-run] delete s3://{path}")
        return
    try:
        import s3fs

        fs = s3fs.S3FileSystem()
        # Per-object deletes: MinIO rejects s3fs's batch DeleteObjects without Content-MD5.
        for key in fs.find(path):
            fs.rm_file(key)
        print(f"deleted (or not found): s3://{path}")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"WARNING: could not delete s3://{path}: {exc}", file=sys.stderr)


def cleanup(dry_run: bool = False) -> None:
    ns = _namespace()
    _kubectl_delete(ns, "-f", _MANIFEST, dry_run=dry_run)
    _kubectl_delete(ns, "pvc", "data-feast-redis-0", dry_run=dry_run)
    _kubectl_delete(ns, "secret", "feast-redis", dry_run=dry_run)
    _delete_s3_prefix(f"{ns}-data/{_S3_PREFIX}", dry_run=dry_run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print commands without executing"
    )
    args = parser.parse_args()
    cleanup(dry_run=args.dry_run)
