"""Create or update the namespace's MLflow credentials Secret."""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys

_SECRET_NAME = "mlflow-credentials"
_CRED_KEYS = (
    "MLFLOW_TRACKING_URI",
    "MLFLOW_TRACKING_USERNAME",
    "MLFLOW_TRACKING_PASSWORD",
)


def _namespace() -> str:
    with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace") as fh:
        return fh.read().strip()


def _prompt(label: str, secret: bool = False) -> str:
    if secret:
        import getpass

        return getpass.getpass(f"{label}: ").strip()
    return input(f"{label}: ").strip()


def _secret_exists(namespace: str) -> bool:
    result = subprocess.run(
        [
            "kubectl",
            "get",
            "secret",
            _SECRET_NAME,
            "-n",
            namespace,
            "-o",
            "name",
            "--ignore-not-found",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Could not check for an existing secret:\n{result.stderr}")
    return bool(result.stdout.strip())


def setup_mlflow_credentials(
    uri: str | None = None,
    username: str | None = None,
    password: str | None = None,
    rerun: bool = False,
) -> None:
    """Create the ``mlflow-credentials`` secret if it doesn't already exist.

    Any parameter left as ``None`` will be requested interactively.

    Pass ``rerun=True`` to replace an existing secret.
    """
    ns = _namespace()
    if not rerun and _secret_exists(ns):
        print(
            f"Secret '{_SECRET_NAME}' already exists in namespace '{ns}'; skipping. "
            "Run `setup_mlflow_credentials(rerun=True)` to replace it."
        )
        return

    if uri is None:
        print("MLflow tracking URI — typically https://<your-cluster-domain>/mlflow/")
        uri = _prompt("MLFLOW_TRACKING_URI")
    if username is None:
        username = _prompt("MLFLOW_TRACKING_USERNAME (your login e-mail)")
    if password is None:
        password = _prompt(
            "MLFLOW_TRACKING_PASSWORD (Personal Access Token)", secret=True
        )

    if not uri or not username or not password:
        raise ValueError(
            "MLFLOW_TRACKING_URI, MLFLOW_TRACKING_USERNAME, and "
            "MLFLOW_TRACKING_PASSWORD must all be non-empty."
        )

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


def _read_secret() -> dict[str, str] | None:
    """Return the decoded secret data, or None if the secret doesn't exist."""
    result = subprocess.run(
        ["kubectl", "get", "secret", _SECRET_NAME, "-n", _namespace(), "-o", "json"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    data = json.loads(result.stdout)["data"]
    return {k: base64.b64decode(data[k]).decode() for k in _CRED_KEYS}


def load_mlflow_credentials() -> dict[str, str]:
    """Resolve MLflow tracking credentials and set them on ``os.environ``.

    Resolution order:

    1. ``MLFLOW_TRACKING_URI`` / ``_USERNAME`` / ``_PASSWORD`` already set in
       the environment (e.g. filled in manually in a notebook cell) — use
       this to avoid the shared secret entirely.
    2. The ``mlflow-credentials`` Kubernetes secret, created by running this
       file interactively from a notebook.

    Also sets ``MLFLOW_ENABLE_PROXY_MULTIPART_UPLOAD=true``. Raises
    ``RuntimeError`` with actionable guidance if neither source is available.
    """
    if all(os.environ.get(k) for k in _CRED_KEYS):
        creds = {k: os.environ[k] for k in _CRED_KEYS}
    else:
        creds = _read_secret()
        if creds is None:
            raise RuntimeError(
                "MLflow credentials not found. Either:\n"
                "  1. Run `%run ~/examples/src/pk_helpers/mlflow_credentials.py` "
                "in a notebook cell, or\n"
                "  2. Set MLFLOW_TRACKING_URI / MLFLOW_TRACKING_USERNAME / "
                "MLFLOW_TRACKING_PASSWORD directly in a notebook cell before "
                "calling load_mlflow_credentials()."
            )
        os.environ.update(creds)
    os.environ["MLFLOW_ENABLE_PROXY_MULTIPART_UPLOAD"] = "true"
    return creds


def require_mlflow_secret() -> None:
    """Fail fast if the ``mlflow-credentials`` K8s secret does not exist.

    Use this before building/submitting a KFP pipeline that injects MLflow
    credentials into task pods via ``use_secret_as_env``. Unlike
    ``load_mlflow_credentials()``, there is no environment-variable
    fallback here: pipeline task pods run in their own containers and can
    only read credentials from the K8s secret (which is also the more
    secure option, since the raw token never appears in the pipeline
    definition), so the secret must exist regardless of what's set in the
    notebook's own environment.
    """
    if _read_secret() is None:
        raise RuntimeError(
            "mlflow-credentials secret not found. This pipeline injects "
            "MLflow credentials into its task pods from that secret, so it "
            "must exist in the cluster (setting MLFLOW_TRACKING_* env vars "
            "in the notebook itself is not enough).\n"
            "Run `%run ~/examples/src/pk_helpers/mlflow_credentials.py` in a "
            "notebook cell to create it."
        )


def main() -> None:
    """Console-script entry point: create/update the MLflow credentials secret."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--uri", default=None, help="MLFLOW_TRACKING_URI")
    parser.add_argument("--username", default=None, help="MLFLOW_TRACKING_USERNAME")
    parser.add_argument(
        "--password", default=None, help="MLFLOW_TRACKING_PASSWORD (PAT)"
    )
    parser.add_argument(
        "--rerun",
        action="store_true",
        help="Replace the secret even if it already exists",
    )
    args = parser.parse_args()

    try:
        setup_mlflow_credentials(
            args.uri, args.username, args.password, rerun=args.rerun
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
