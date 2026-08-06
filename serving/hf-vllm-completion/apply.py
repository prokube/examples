"""
Deploy the DistilBERT CPU InferenceService (HuggingFace backend) and smoke-test it.

The model (distilbert-base-uncased-finetuned-sst-2-english, ~250 MB) is
downloaded from the HuggingFace Hub on first start, so the ISVC may take a
few minutes to become ready.

Usage
-----
    python apply.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

_ISVC_NAME = "distilbert-inf-serv"
_MODEL_NAME = "distilbert"
_YAML = os.path.join(os.path.dirname(__file__), "inference-service-cpu.yaml")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _namespace() -> str:
    with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace") as fh:
        return fh.read().strip()


def _kubectl_apply(manifest: str, namespace: str) -> None:
    result = subprocess.run(
        ["kubectl", "apply", "-f", "-", "-n", namespace],
        input=manifest,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    print(result.stdout.strip())


def _wait_isvc_ready(name: str, namespace: str, timeout: int) -> None:
    print(
        f"Waiting for InferenceService '{name}' to become ready (timeout {timeout}s)..."
    )
    result = subprocess.run(
        [
            "kubectl",
            "wait",
            "inferenceservice",
            name,
            "--for=condition=Ready",
            f"--timeout={timeout}s",
            "-n",
            namespace,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Dump ISVC status to help diagnose
        subprocess.run(
            ["kubectl", "describe", "inferenceservice", name, "-n", namespace],
            check=False,
        )
        raise RuntimeError(
            f"InferenceService '{name}' did not become ready within {timeout}s:\n"
            + (result.stderr or result.stdout)
        )


def _smoke_test(namespace: str, timeout: int = 120) -> None:
    """POST to the internal cluster URL; retries until the model responds."""
    _root = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True
    ).strip()
    sys.path.insert(0, os.path.join(_root, "scripts"))
    from kserve_internal_url import internal_predict_url  # noqa: PLC0415

    url = internal_predict_url(_ISVC_NAME, namespace, _MODEL_NAME)
    payload = json.dumps({"instances": ["KServe is wonderful!"]}).encode()
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read())
            if "predictions" not in body:
                raise RuntimeError(f"unexpected response body: {body}")
            print(f"Smoke test passed: {body}")
            return
        except Exception as exc:
            last_err = exc
            time.sleep(5)
    raise RuntimeError(f"Smoke test failed after {timeout}s: {last_err}")


# ── Entry point ───────────────────────────────────────────────────────────────


def deploy(timeout: int = 900) -> None:
    ns = _namespace()

    with open(_YAML) as fh:
        manifest = fh.read()

    _kubectl_apply(manifest, ns)
    print(f"Applied InferenceService '{_ISVC_NAME}' in namespace '{ns}'.")

    _wait_isvc_ready(_ISVC_NAME, ns, timeout)
    print(f"InferenceService '{_ISVC_NAME}' is ready.")

    _smoke_test(ns)


if __name__ == "__main__":
    try:
        deploy()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
