"""
Utility to create or retrieve a prokube API key for use in examples.

Usage from a notebook
---------------------
    import sys, subprocess, os
    _root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
    sys.path.insert(0, os.path.join(_root, "scripts"))
    from get_or_create_api_key import get_or_create_api_key

    API_KEY = get_or_create_api_key()

CLI usage
---------
    python get_or_create_api_key.py
    # prints the key to stdout

Resolution order
----------------
The function returns a usable model-serving API key, choosing the mechanism
that fits the deployment it runs on:

1. **New deployments (AI Gateway).**  If the ``AIGatewayKey`` CRD is present,
   the key is stored as an AIGatewayKey CR named ``examples-key`` backed by a
   Secret named ``examples-key-secret`` in the notebook's namespace.  Both
   resources are created if they do not already exist.  Re-running is safe.

2. **Older deployments (hardcoded EnvoyFilter).**  Older clusters do not have
   the AIGatewayKey CRD; instead an admin pre-provisions a single API key and
   injects it into the notebook pod via the ``INFERENCE_SERVICE_API_KEY``
   environment variable.  When the CRD is absent, that env var is used.

3. **Fallback.**  If neither is available, the caller is prompted to paste the
   key interactively, so the example degrades gracefully instead of crashing.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import subprocess
import sys
from getpass import getpass

_KEY_NAME = "examples-key"
_SECRET_NAME = "examples-key-secret"

# Env var an admin injects into the notebook pod on older (pre-AI-Gateway)
# deployments that rely on a hardcoded EnvoyFilter for auth.
_API_KEY_ENV_VAR = "INFERENCE_SERVICE_API_KEY"


def _namespace() -> str:
    with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace") as fh:
        return fh.read().strip()


def _kubectl(*args: str, input: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["kubectl", *args],
        input=input,
        capture_output=True,
        text=True,
    )


def _aigatewaykey_crd_available() -> bool:
    """Return True if the AIGatewayKey CRD is registered in the cluster.

    Uses the API discovery endpoint (kubectl api-resources) rather than
    directly reading the CRD object, because notebook pod service accounts
    typically lack RBAC permission to get cluster-scoped CRD resources.
    API discovery is allowed for all authenticated Kubernetes users.
    """
    result = _kubectl(
        "api-resources",
        "--api-group=prokube.ai",
        "-o",
        "name",
        "--no-headers",
    )
    return result.returncode == 0 and "aigatewaykeys" in result.stdout


def _key_exists(namespace: str) -> bool:
    result = _kubectl(
        "get", "aigatewaykey", _KEY_NAME, "-n", namespace, "--ignore-not-found"
    )
    return bool(result.stdout.strip())


def _read_key_from_secret(namespace: str) -> str:
    result = _kubectl("get", "secret", _SECRET_NAME, "-n", namespace, "-o", "json")
    if result.returncode != 0:
        raise RuntimeError(f"Could not read secret {_SECRET_NAME}:\n{result.stderr}")
    data = json.loads(result.stdout)["data"]
    return base64.b64decode(data["token"]).decode()


def _apply(manifest: str, namespace: str) -> None:
    result = _kubectl("apply", "-n", namespace, "-f", "-", input=manifest)
    if result.returncode != 0:
        raise RuntimeError(f"kubectl apply failed:\n{result.stderr}")


def _owner(namespace: str) -> str:
    """Determine the key owner.

    Tries to read MLFLOW_TRACKING_USERNAME from the mlflow-credentials secret
    (the canonical identity in the prokube platform).  Falls back to a
    namespace-scoped placeholder if the secret is absent.
    """
    result = _kubectl(
        "get",
        "secret",
        "mlflow-credentials",
        "-n",
        namespace,
        "-o",
        "jsonpath={.data.MLFLOW_TRACKING_USERNAME}",
    )
    if result.returncode == 0 and result.stdout.strip():
        return base64.b64decode(result.stdout.strip()).decode()
    return f"notebook-examples@{namespace}"


def _create_key(namespace: str) -> str:
    key_value = f"pk_live_{secrets.token_hex(20)}"
    owner = _owner(namespace)

    _apply(
        f"apiVersion: v1\n"
        f"kind: Secret\n"
        f"metadata:\n"
        f"  name: {_SECRET_NAME}\n"
        f"  namespace: {namespace}\n"
        f"stringData:\n"
        f"  token: {key_value}\n",
        namespace,
    )

    _apply(
        f"apiVersion: prokube.ai/v1alpha1\n"
        f"kind: AIGatewayKey\n"
        f"metadata:\n"
        f"  name: {_KEY_NAME}\n"
        f"  namespace: {namespace}\n"
        f"spec:\n"
        f"  displayName: Examples API key\n"
        f"  owner: {owner}\n"
        f"  secretRef:\n"
        f"    name: {_SECRET_NAME}\n"
        f"    key: token\n"
        f"  scopes:\n"
        f"    - type: workspace\n",
        namespace,
    )

    return key_value


def _key_from_env() -> str | None:
    """Return the admin-provisioned API key from the environment, if set."""
    value = os.environ.get(_API_KEY_ENV_VAR, "").strip()
    return value or None


def get_or_create_api_key(ns=None) -> str:
    """Return a model-serving API key for the current namespace.

    See the module docstring for the resolution order: AIGatewayKey CR on new
    deployments, the ``INFERENCE_SERVICE_API_KEY`` env var on older ones, and an
    interactive prompt as a last resort.
    """
    # New deployments: manage an AIGatewayKey CR (fully automated).
    if _aigatewaykey_crd_available():
        ns = ns or _namespace()
        if _key_exists(ns):
            return _read_key_from_secret(ns)
        return _create_key(ns)

    # Older deployments: admin injects the key via an env var.
    env_key = _key_from_env()
    if env_key:
        return env_key

    # Fallback: prompt instead of crashing.
    key = getpass(
        f"AIGatewayKey CRD not found and ${_API_KEY_ENV_VAR} is unset. "
        "Please enter the model-serving API key (ask your cluster admin): "
    ).strip()
    if not key:
        raise RuntimeError(
            "No API key available: the AIGatewayKey CRD is absent, "
            f"${_API_KEY_ENV_VAR} is unset, and no key was entered."
        )
    return key


if __name__ == "__main__":
    try:
        argparser = argparse.ArgumentParser(
            description="Get or create a prokube API key"
        )
        argparser.add_argument(
            "--namespace",
            "-n",
            help="The Kubernetes namespace to use (defaults to the pods namespace)",
        )
        args = argparser.parse_args()
        print(get_or_create_api_key(args.namespace))
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
