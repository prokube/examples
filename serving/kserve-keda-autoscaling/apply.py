"""Deploy a KEDA-scaled InferenceService and verify it actually scales under load."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request

_ISVC_NAME = "opt-125m"
_SCALED_OBJECT_NAME = "opt-125m-scaledobject"
# In RawDeployment mode KServe names the Deployment {isvc-name}-predictor.
_DEPLOYMENT_NAME = "opt-125m-predictor"
_ISVC_YAML = os.path.join(os.path.dirname(__file__), "inference-service.yaml")
_SO_YAML = os.path.join(os.path.dirname(__file__), "scaled-object.yaml")
_LOAD_GENERATOR = os.path.join(os.path.dirname(__file__), "load-generator.py")


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
    """Apply the ScaledObject, returning an error only when KEDA is absent."""
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


def _wait_scaledobject_ready(name: str, namespace: str, timeout: int = 60) -> None:
    """Poll until KEDA accepts the ScaledObject (Ready=True). Unlike
    'Active', this doesn't require traffic to have been sent yet."""
    print(f"Waiting for ScaledObject '{name}' to be accepted by KEDA...")
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
                "jsonpath={.status.conditions[?(@.type=='Ready')].status}",
            ],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(
                f"'kubectl get scaledobject {name}' failed:\n{r.stderr or r.stdout}"
            )
        if r.stdout.strip() == "True":
            print(f"ScaledObject '{name}' is ready.")
            return
        time.sleep(5)
    raise RuntimeError(
        f"ScaledObject '{name}' did not become ready within {timeout}s. "
        "Check 'kubectl describe scaledobject' for trigger/auth errors."
    )


def _get_ready_replicas(name: str, namespace: str) -> int:
    r = subprocess.run(
        [
            "kubectl",
            "get",
            "deployment",
            name,
            "-n",
            namespace,
            "-o",
            "jsonpath={.status.readyReplicas}",
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(
            f"'kubectl get deployment {name}' failed:\n{r.stderr or r.stdout}"
        )
    return int(r.stdout.strip() or 0)


def _get_scaledobject_active(name: str, namespace: str) -> str:
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
    return r.stdout.strip() if r.returncode == 0 else "unknown"


def _scale_up_diagnostics(namespace: str) -> str:
    commands = [
        [
            "kubectl",
            "get",
            "pods",
            "-l",
            f"serving.kserve.io/inferenceservice={_ISVC_NAME}",
            "-o",
            "wide",
            "-n",
            namespace,
        ],
        [
            "kubectl",
            "describe",
            "pods",
            "-l",
            f"serving.kserve.io/inferenceservice={_ISVC_NAME}",
            "-n",
            namespace,
        ],
        [
            "kubectl",
            "get",
            "hpa",
            f"keda-hpa-{_SCALED_OBJECT_NAME}",
            "-o",
            "wide",
            "-n",
            namespace,
        ],
        [
            "kubectl",
            "describe",
            "hpa",
            f"keda-hpa-{_SCALED_OBJECT_NAME}",
            "-n",
            namespace,
        ],
    ]
    diagnostics = []
    for command in commands:
        label = " ".join(command)
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=5, check=False
            )
            output = "\n".join(
                part.strip()
                for part in (result.stdout, result.stderr)
                if part.strip()
            )
            diagnostics.append(f"$ {label}\n{output or '(no output)'}")
        except Exception as exc:
            diagnostics.append(f"$ {label}\nDiagnostic failed: {exc}")
    return "\n\n".join(diagnostics)


def _verify_autoscaling(
    namespace: str, target_replicas: int = 2, timeout: int = 600
) -> None:
    """Drive sustained load (stable-2 preset, ~8 tok/s) and confirm the
    Deployment actually scales up — a single request never crosses the
    Prometheus threshold, so replica count alone proves autoscaling works."""
    print(
        f"Generating load (stable-2 preset, ~8 tok/s) to verify scale-up to "
        f"{target_replicas} replicas (timeout {timeout}s)..."
    )
    url = f"http://{_DEPLOYMENT_NAME}.{namespace}.svc.cluster.local/openai/v1/completions"
    proc = subprocess.Popen(
        [
            sys.executable,
            _LOAD_GENERATOR,
            "--mode",
            "stable-2",
            "--url",
            url,
            "--model",
            _ISVC_NAME,
            "--duration",
            str(timeout),
        ],
    )
    try:
        deadline = time.time() + timeout
        while time.time() < deadline:
            ready = _get_ready_replicas(_DEPLOYMENT_NAME, namespace)
            if ready >= target_replicas:
                active = _get_scaledobject_active(_SCALED_OBJECT_NAME, namespace)
                print(
                    f"Deployment '{_DEPLOYMENT_NAME}' scaled to {ready} replica(s) "
                    f"(ScaledObject Active={active}) — autoscaling verified."
                )
                return
            time.sleep(10)
        raise RuntimeError(
            f"Deployment '{_DEPLOYMENT_NAME}' did not scale to {target_replicas} "
            f"replicas within {timeout}s under sustained load. Check "
            "'kubectl describe scaledobject', the HPA, and Prometheus connectivity."
            f"\n\nScale-up diagnostics:\n{_scale_up_diagnostics(namespace)}"
        )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


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

    # Apply ScaledObject — detect KEDA availability via the apply itself rather
    # than 'kubectl get crd' which requires cluster-level RBAC notebook SAs lack.
    with open(_SO_YAML) as fh:
        so_manifest = fh.read()
    skip_reason = _try_apply_scaledobject(so_manifest, ns)
    if skip_reason:
        raise RuntimeError(
            "KEDA is not installed in this cluster "
            f"(kubectl apply returned: {skip_reason}).\n"
            "This example is opt-in (--include-keda) specifically because it "
            "requires KEDA — install KEDA in the cluster, or omit --include-keda."
        )
    print(f"Applied ScaledObject '{_SCALED_OBJECT_NAME}' in namespace '{ns}'.")

    _wait_isvc_ready(_ISVC_NAME, ns, timeout)
    print(f"InferenceService '{_ISVC_NAME}' is ready.")

    _wait_scaledobject_ready(_SCALED_OBJECT_NAME, ns)
    _smoke_test(ns)
    _verify_autoscaling(ns)


if __name__ == "__main__":
    try:
        deploy()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
