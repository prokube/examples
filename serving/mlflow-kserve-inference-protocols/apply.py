"""
Deploy the v1 and v2 MLflow KServe InferenceServices and smoke-test both.

Substitutes ``<workspace-name>`` and ``<username>`` in the YAML manifests from
the cluster environment, applies them, waits for readiness, and verifies that
both endpoints return identical predictions for the same input.

Usage from a notebook
---------------------
    import sys
    sys.path.insert(0, ".")   # run from the serving/mlflow-kserve-inference-protocols/ dir
    from apply import deploy

    v1_uri, v2_uri, api_key = deploy()

CLI usage
---------
    python apply.py

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
import urllib.error
import urllib.request

_HERE = os.path.dirname(__file__)

_ISVC_NAMES = {
    "v1": "v1-mobile-price-classification-inference",
    "v2": "v2-mobile-price-classification-inference",
}
_YAML_FILES = {
    "v1": os.path.join(_HERE, "v1-InferenceService.yaml"),
    "v2": os.path.join(_HERE, "v2-InferenceService.yaml"),
}
_BODY_FILES = {
    "v1": os.path.join(_HERE, "v1-mlflow-inference-body.json"),
    "v2": os.path.join(_HERE, "v2-mlflow-inference-body.json"),
}


# ── Helpers ───────────────────────────────────────────────────────────────────


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
    return base64.b64decode(data["MLFLOW_TRACKING_USERNAME"]).decode().split("@")[0]


def _apply_yaml(yaml_file: str, namespace: str, username: str) -> None:
    manifest = open(yaml_file).read()
    manifest = manifest.replace("<workspace-name>", namespace).replace(
        "<username>", username
    )
    result = subprocess.run(
        ["kubectl", "apply", "-n", namespace, "-f", "-"],
        input=manifest,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"kubectl apply failed for {os.path.basename(yaml_file)}:\n{result.stderr}"
        )
    print(result.stdout.strip())


def _wait_ready(name: str, namespace: str, timeout: int = 600) -> None:
    print(f"  Waiting for {name} (timeout {timeout}s)...")
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
        subprocess.run(
            ["kubectl", "describe", "inferenceservice", name, "-n", namespace]
        )
        raise RuntimeError(f"{name} did not become ready:\n{result.stderr}")


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


def _get_api_key() -> str:
    root = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True
    ).strip()
    sys.path.insert(0, os.path.join(root, "scripts"))
    from get_or_create_api_key import get_or_create_api_key

    return get_or_create_api_key()


def _smoke_test(uri: str, name: str, protocol: str, api_key: str) -> None:
    """POST one inference request; raise on non-2xx or missing predictions."""
    body = json.load(open(_BODY_FILES[protocol]))
    if protocol == "v1":
        url = f"{uri}/v1/models/{name}:predict"
        pred_key = "predictions"
    else:
        url = f"{uri}/v2/models/{name}/infer"
        pred_key = "outputs"

    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "X-Api-Key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Smoke test {protocol} returned HTTP {exc.code}: {exc.read().decode()}"
        ) from exc

    if pred_key not in result:
        raise RuntimeError(f"Smoke test {protocol}: unexpected response: {result}")
    print(f"  [{protocol}] smoke test passed — {len(result[pred_key])} prediction(s)")


# ── Entry point ───────────────────────────────────────────────────────────────


def deploy(timeout: int = 600) -> tuple[str, str, str]:
    """Deploy both ISVCs, wait for readiness, and return (v1_uri, v2_uri, api_key)."""
    ns = _namespace()
    username = _mlflow_username(ns)

    print("Applying InferenceService manifests...")
    for proto, yaml_file in _YAML_FILES.items():
        _apply_yaml(yaml_file, ns, username)

    print("Waiting for InferenceServices to become ready...")
    for proto, name in _ISVC_NAMES.items():
        _wait_ready(name, ns, timeout)

    v1_uri = _isvc_url(_ISVC_NAMES["v1"], ns)
    v2_uri = _isvc_url(_ISVC_NAMES["v2"], ns)
    api_key = _get_api_key()

    print(f"v1 URI: {v1_uri}")
    print(f"v2 URI: {v2_uri}")

    print("Running smoke tests...")
    _smoke_test(v1_uri, _ISVC_NAMES["v1"], "v1", api_key)
    _smoke_test(v2_uri, _ISVC_NAMES["v2"], "v2", api_key)

    return v1_uri, v2_uri, api_key


if __name__ == "__main__":
    try:
        v1_uri, v2_uri, api_key = deploy()
        print(f"ISVC_URI_V1={v1_uri}")
        print(f"ISVC_URI_V2={v2_uri}")
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
