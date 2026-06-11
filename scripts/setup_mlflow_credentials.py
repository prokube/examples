"""
One-time setup: store MLflow credentials in a Kubernetes secret so that
example notebooks can read them without hardcoded values.

This is the only step in the automation plan that requires human input —
the MLflow Personal Access Token (PAT) must be created via the MLflow UI
(Permissions → Create access key) and cannot be obtained programmatically.

Usage from a notebook
---------------------
    import sys, subprocess, os
    _root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
    sys.path.insert(0, os.path.join(_root, "scripts"))
    from setup_mlflow_credentials import setup_mlflow_credentials

    setup_mlflow_credentials(
        uri="https://my-cluster.example.com/mlflow/",
        username="alice@example.com",
        password="<paste PAT here>",
    )

CLI usage (any argument can be omitted; you will be prompted for it)
---------------------------------------------------------------------
    python setup_mlflow_credentials.py \\
        --uri https://my-cluster.example.com/mlflow/ \\
        --username alice@example.com \\
        --password <paste PAT here>

The credentials are stored in a Secret named ``mlflow-credentials`` in the
notebook's namespace.  Re-running updates the secret in place.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

_SECRET_NAME = "mlflow-credentials"


def _namespace() -> str:
    with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace") as fh:
        return fh.read().strip()


def _prompt(label: str, secret: bool = False) -> str:
    if secret:
        import getpass

        return getpass.getpass(f"{label}: ")
    return input(f"{label}: ").strip()


def setup_mlflow_credentials(
    uri: str | None = None,
    username: str | None = None,
    password: str | None = None,
) -> None:
    """Create or update the ``mlflow-credentials`` secret.

    Any parameter left as ``None`` will be requested interactively.
    """
    if uri is None:
        print("MLflow tracking URI — typically https://<your-cluster-domain>/mlflow/")
        uri = _prompt("MLFLOW_TRACKING_URI")
    if username is None:
        username = _prompt("MLFLOW_TRACKING_USERNAME (your login e-mail)")
    if password is None:
        password = _prompt(
            "MLFLOW_TRACKING_PASSWORD (Personal Access Token)", secret=True
        )

    ns = _namespace()

    result = subprocess.run(
        [
            "kubectl",
            "create",
            "secret",
            "generic",
            _SECRET_NAME,
            "-n",
            ns,
            f"--from-literal=MLFLOW_TRACKING_URI={uri}",
            f"--from-literal=MLFLOW_TRACKING_USERNAME={username}",
            f"--from-literal=MLFLOW_TRACKING_PASSWORD={password}",
            "--save-config",
            "--dry-run=client",
            "-o",
            "yaml",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    apply = subprocess.run(
        ["kubectl", "apply", "-n", ns, "-f", "-"],
        input=result.stdout,
        capture_output=True,
        text=True,
    )
    if apply.returncode != 0:
        raise RuntimeError(f"kubectl apply failed:\n{apply.stderr}")

    print(f"Secret '{_SECRET_NAME}' created/updated in namespace '{ns}'.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--uri", default=None, help="MLFLOW_TRACKING_URI")
    parser.add_argument("--username", default=None, help="MLFLOW_TRACKING_USERNAME")
    parser.add_argument(
        "--password", default=None, help="MLFLOW_TRACKING_PASSWORD (PAT)"
    )
    args = parser.parse_args()

    try:
        setup_mlflow_credentials(args.uri, args.username, args.password)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
