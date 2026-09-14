"""Delete the object-storage InferenceService."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


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


def _delete_s3_model(namespace: str, dry_run: bool = False) -> None:
    s3_path = f"{namespace}-data/minimal-kserve-example/model.joblib"
    if dry_run:
        print(f"[dry-run] delete s3://{s3_path}")
        return
    try:
        import s3fs

        fs = s3fs.S3FileSystem()
        if fs.exists(s3_path):
            fs.rm(s3_path)
            print(f"deleted s3://{s3_path}")
        else:
            print(f"s3://{s3_path} not found (already deleted)")
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: could not delete s3://{s3_path}: {exc}", file=sys.stderr)


def _delete_local_artifacts(dry_run: bool = False) -> None:
    script_dir = Path(__file__).parent
    for name in ("model.joblib", "inferenceservice.yaml"):
        path = script_dir / name
        if dry_run:
            print(f"[dry-run] delete {path}")
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            print(f"WARNING: could not delete {path}: {exc}", file=sys.stderr)


def cleanup(dry_run: bool = False) -> None:
    ns = _namespace()

    _kubectl_delete(
        "inferenceservice", "kserve-object-storage-test", "-n", ns, dry_run=dry_run
    )
    _delete_s3_model(ns, dry_run=dry_run)
    _delete_local_artifacts(dry_run=dry_run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print commands without executing them"
    )
    args = parser.parse_args()
    cleanup(dry_run=args.dry_run)
