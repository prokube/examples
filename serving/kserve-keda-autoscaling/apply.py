"""
Deploy the KEDA autoscaling example (OPT-125M, vLLM backend, CPU) and verify
that both the InferenceService and the ScaledObject become active.

KEDA CRD check
--------------
If the ``scaledobjects.keda.sh`` CRD is absent the script exits with 0 and a
SKIP message rather than failing — the example is opt-in because KEDA is not
installed in every prokube cluster.

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

_ISVC_NAME = "opt-125m"
_SCALED_OBJECT_NAME = "opt-125m-scaledobject"
_ISVC_YAML = os.path.join(os.path.dirname(__file__), "inference-service.yaml")
_SO_YAML = os.path.join(os.path.dirname(__file__), "scaled-object.yaml")


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


def _try_apply_scaledobject(manifest: str, namespace: str) -> str | None:
    """Apply the ScaledObject manifest; return an error string if KEDA is absent.

    Returns None on success, or a non-empty string if kubectl rejected the
    manifest because the ScaledObject CRD is not installed.  Any other error
    is raised so CI marks the example as FAIL instead of silently skipping.
    """
    result = subprocess.run(
        ["kubectl", "apply", "-f", "-", "-n", namespace],
        input=manifest,
        text=True,
        capture_output=True,
    )
    if result.returncode == 0:
        print(result.stdout.strip())
        return None
    stderr = result.stderr or result.stdout
    if (
        "no matches for kind" in stderr
        or "the server doesn't have a resource type" in stderr
    ):
        return stderr.strip()
    raise RuntimeError(stderr)


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
        subprocess.run(
            ["kubectl", "describe", "inferenceservice", name, "-n", namespace],
            check=False,
        )
        raise RuntimeError(
            f"InferenceService '{name}' did not become ready within {timeout}s:\n"
            + (result.stderr or result.stdout)
        )


def _wait_scaledobject_active(name: str, namespace: str, timeout: int = 120) -> None:
    """Poll until KEDA reports the ScaledObject as Active=True."""
    print(f"Waiting for ScaledObject '{name}' to become active...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = subprocess.run(
            [
                "kubectl",
                "get",
                "scaledobject",
                name,
                "-n",
                namespace,
                "-o",
                "jsonpath={.status.conditions[?(@.type=='Active')].status}",
            ],
            capture_output=True,
            text=True,
        )
        if r.stdout.strip() == "True":
            print(f"ScaledObject '{name}' is active.")
            return
        time.sleep(10)
    raise RuntimeError(
        f"ScaledObject '{name}' did not become active within {timeout}s. "
        "Check 'kubectl describe scaledobject' for trigger errors."
    )


def _smoke_test(namespace: str, timeout: int = 60) -> None:
    """Send a single completion request via the cluster-internal predictor Service."""
    # RawDeployment mode exposes the predictor as a plain Kubernetes Service named
    # <isvc-name>-predictor — no external gateway or API key required.
    url = (
        f"http://opt-125m-predictor.{namespace}.svc.cluster.local/openai/v1/completions"
    )
    payload = json.dumps(
        {"model": "opt-125m", "prompt": "KServe is", "max_tokens": 8}
    ).encode()
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
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = json.loads(resp.read())
            if "choices" not in body:
                raise RuntimeError(f"unexpected response body: {body}")
            text = body["choices"][0].get("text", "")
            print(f"Smoke test passed: {text!r}")
            return
        except Exception as exc:
            last_err = exc
            time.sleep(5)
    raise RuntimeError(f"Smoke test failed after {timeout}s: {last_err}")


# ── Entry point ───────────────────────────────────────────────────────────────


def deploy(timeout: int = 900) -> None:
    ns = _namespace()

    with open(_ISVC_YAML) as fh:
        isvc_manifest = fh.read()
    _kubectl_apply(isvc_manifest, ns)
    print(f"Applied InferenceService '{_ISVC_NAME}' in namespace '{ns}'.")

    _wait_isvc_ready(_ISVC_NAME, ns, timeout)
    print(f"InferenceService '{_ISVC_NAME}' is ready.")

    # Apply ScaledObject — detect KEDA availability via the apply itself rather
    # than 'kubectl get crd' which requires cluster-level RBAC notebook SAs lack.
    with open(_SO_YAML) as fh:
        so_manifest = fh.read()
    skip_reason = _try_apply_scaledobject(so_manifest, ns)
    if skip_reason:
        print(
            f"SKIP: KEDA is not installed in this cluster "
            f"(kubectl apply returned: {skip_reason}).\n"
            "The ScaledObject was not created; the ISVC is running without autoscaling."
        )
        sys.exit(0)
    print(f"Applied ScaledObject '{_SCALED_OBJECT_NAME}' in namespace '{ns}'.")

    _wait_scaledobject_active(_SCALED_OBJECT_NAME, ns)
    _smoke_test(ns)


if __name__ == "__main__":
    try:
        deploy()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
