"""Run registered examples by phase, poll KFP runs, and always clean up."""

from __future__ import annotations

import argparse
import sys

from .runner import run_all


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ci",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--timeout-notebook",
        type=int,
        default=1800,
        help=(
            "Per-cell timeout for notebooks and whole-process timeout for scripts, "
            "in seconds (default: 1800)"
        ),
    )
    parser.add_argument(
        "--timeout-pipeline",
        type=int,
        default=3600,
        help="KFP run poll timeout in seconds (default: 3600)",
    )
    parser.add_argument(
        "--include-keda",
        action="store_true",
        help="Include KEDA autoscaling example (opt-in; requires KEDA in the cluster; runs on CPU)",
    )
    parser.add_argument(
        "--include-shadow",
        action="store_true",
        help=(
            "Include minimal-example-shadow-deployment (opt-in; "
            "requires CrunchyData postgres-operator; Istio VirtualService not tested)"
        ),
    )
    parser.add_argument(
        "--include-pytorch",
        action="store_true",
        help="Include pytorch_lightning examples (opt-in; requires pytorch in the notebook image)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan without executing anything",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=8,
        help=(
            "Max examples run concurrently (default: 8). Lower this if the "
            "notebook pod is being OOM-killed by running too many examples "
            "at once."
        ),
    )
    args = parser.parse_args()

    results = run_all(
        timeout_notebook=args.timeout_notebook,
        timeout_pipeline=args.timeout_pipeline,
        include_keda=args.include_keda,
        include_shadow=args.include_shadow,
        include_pytorch=args.include_pytorch,
        dry_run=args.dry_run,
        max_workers=args.max_workers,
    )

    failed = sum(1 for r in results.values() if r.status == "FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
