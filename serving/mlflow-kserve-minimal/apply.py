"""
Deploy the mlflow-kserve-minimal InferenceService and run an inference test.

Substitutes ``<workspace-name>`` and ``<your-user>`` in InferenceService.yaml
from the cluster environment, applies it, waits for readiness, runs a smoke
test via ``test_inference_service.py``, and prints the external URL.

Usage from a notebook
---------------------
    import sys, subprocess, os
    _root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
    sys.path.insert(0, os.path.join(_root, "serving", "mlflow-kserve-minimal"))
    from apply import deploy

    isvc_uri = deploy()

CLI usage
---------
    python apply.py
    # prints ISVC_URI=<url> and runs inference smoke test

Prerequisites
-------------
- ``mlflow-credentials`` secret must exist (run scripts/setup_mlflow_credentials.py).
- The MLflow model ``mobile-price-svm-<username>`` version 1 must be registered
  (run mlflow/mobile-price-classification/mlflow-mobile-price-classification.ipynb first).
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys

_ISVC_NAME = "mobile-price-svm"
_YAML_TEMPLATE = os.path.join(os.path.dirname(__file__), "InferenceService.yaml")


def _namespace() -> str:
    with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace") as fh:
        return fh.read().strip()


def _mlflow_username(namespace: str) -> str:
    result = subprocess.run(
        [
            "kubectl",
            "get",
            "secret",
            "mlflow-credentials",
            "-n",
            namespace,
            "-o",
            "json",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "mlflow-credentials secret not found.\n"
            "Run scripts/setup_mlflow_credentials.py to create it."
        )
    data = json.loads(result.stdout)["data"]
    full = base64.b64decode(data["MLFLOW_TRACKING_USERNAME"]).decode()
    # Pipeline registers models as "mobile-price-svm-{local_user}" where
    # local_user = MLFLOW_TRACKING_USERNAME.split('@')[0], e.g.
    # "developer1@prokube.cloud" → "developer1"
    return full.split("@")[0]


def _kubectl_apply(manifest: str, namespace: str) -> None:
    result = subprocess.run(
        ["kubectl", "apply", "-n", namespace, "-f", "-"],
        input=manifest,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"kubectl apply failed:\n{result.stderr}")


def _wait_ready(name: str, namespace: str, timeout: int = 600) -> None:
    print(
        f"Waiting for InferenceService '{name}' to become ready (timeout {timeout}s)..."
    )
    result = subprocess.run(
        [
            "kubectl",
            "wait",
            "inferenceservice",
            name,
            "-n",
            namespace,
            "--for=condition=Ready",
            f"--timeout={timeout}s",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"InferenceService '{name}' did not become ready:\n{result.stderr}"
        )
    print(f"  '{name}' is Ready.")


def _isvc_url(name: str, namespace: str) -> str:
    return subprocess.check_output(
        [
            "kubectl",
            "get",
            "inferenceservice",
            name,
            "-n",
            namespace,
            "-o",
            "jsonpath={.status.url}",
        ],
        text=True,
    ).strip()


def deploy(timeout: int = 600) -> str:
    """Apply InferenceService.yaml, wait for readiness, return the external URL."""
    ns = _namespace()
    username = _mlflow_username(ns)

    with open(_YAML_TEMPLATE) as fh:
        manifest = fh.read()

    manifest = (
        manifest.replace("<inference-name>", _ISVC_NAME)
        .replace("<workspace-name>", ns)
        .replace("<your-user>", username)
    )

    _kubectl_apply(manifest, ns)
    print(f"Applied InferenceService '{_ISVC_NAME}' in namespace '{ns}'.")

    _wait_ready(_ISVC_NAME, ns, timeout=timeout)
    url = _isvc_url(_ISVC_NAME, ns)
    print(f"ISVC_URI={url}")
    return url


_HERE = os.path.dirname(os.path.abspath(__file__))
_TEST_SCRIPT = os.path.join(_HERE, "test_inference_service.py")
_TEST_JSON = os.path.join(_HERE, "v2-mlflow-inference-body.json")


def test(uri: str) -> None:
    """Run the inference smoke test against the deployed ISVC."""
    # Get / create the API key
    _root = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True
    ).strip()
    sys.path.insert(0, os.path.join(_root, "scripts"))
    from get_or_create_api_key import get_or_create_api_key  # noqa: PLC0415

    api_key = get_or_create_api_key()

    print(f"Running inference smoke test against {uri} ...")
    result = subprocess.run(
        [sys.executable, _TEST_SCRIPT, "--json", _TEST_JSON, "--model", _ISVC_NAME],
        capture_output=True,
        text=True,
        env={**os.environ, "API_KEY": api_key, "INFERENCE_SERVICE_URI": uri},
    )
    if result.returncode != 0:
        raise RuntimeError(f"Inference test failed:\n{result.stdout}\n{result.stderr}")
    print("Inference test passed.")
    print(result.stdout.strip())


def deploy_and_test(timeout: int = 600) -> str:
    """Deploy the ISVC, wait for readiness, run smoke test, return the URL."""
    uri = deploy(timeout=timeout)
    test(uri)
    return uri


if __name__ == "__main__":
    try:
        deploy_and_test()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
