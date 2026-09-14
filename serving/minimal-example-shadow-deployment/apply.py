"""Deploy Postgres and the doubler/tripler services, then test the primary."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
import urllib.request
import uuid

_ROOT = os.path.dirname(__file__)

_PG_CLUSTER_NAME = "inferencing-postgres"
_PG_SECRET_NAME = "inferencing-postgres-pguser-transformer-admin"
_PG_HOST_TEMPLATE = "inferencing-postgres-primary.{ns}.svc"
_PG_USER = "transformer-admin"
_PG_DB = "scale-inference"

_DOUBLER_ISVC = "double-minimal-custom-inference"
_TRIPLER_ISVC = "triple-minimal-custom-inference"

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS public.inference_requests (
    request_id   uuid                     NOT NULL,
    request_time timestamp with time zone NULL,
    request_data json                     NULL,
    predict_url  text                     NULL,
    created_at   timestamp                NULL,
    PRIMARY KEY (request_id)
);
CREATE TABLE IF NOT EXISTS public.inference_response (
    request_id    uuid      NOT NULL,
    response_data json      NULL,
    created_at    timestamp NULL,
    PRIMARY KEY (request_id)
);
"""


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
    if result.returncode == 0:
        print(result.stdout.strip())
        return
    stderr = result.stderr or result.stdout
    # Translate common failure modes into actionable messages
    if (
        "no matches for kind" in stderr
        or "the server doesn't have a resource type" in stderr
    ):
        raise RuntimeError(
            "postgres-operator is not installed in this cluster. "
            "The shadow deployment example requires the CrunchyData postgres-operator."
        )
    if "Forbidden" in stderr and "postgres-operator.crunchydata.com" in stderr:
        raise RuntimeError(
            "The notebook ServiceAccount lacks RBAC permission to manage PostgresCluster "
            "resources.\n"
            "Ask your cluster admin to grant get/create/update/patch on "
            "postgresclusters.postgres-operator.crunchydata.com in this namespace."
        )
    raise RuntimeError(stderr)


def _wait_for_secret(name: str, namespace: str, timeout: int = 300) -> None:
    """Block until the CrunchyData operator creates the user secret."""
    print(
        f"Waiting for secret '{name}' to appear (postgres-operator creates it after cluster init)..."
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = subprocess.run(
            ["kubectl", "get", "secret", name, "-n", namespace],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            return
        time.sleep(10)
    raise RuntimeError(
        f"Secret '{name}' did not appear within {timeout}s. "
        "Check the PostgresCluster status."
    )


def _wait_pod_exists(label_selector: str, namespace: str, timeout: int) -> None:
    """Poll until a matching pod exists ('kubectl wait' errors instead of
    blocking if the operator hasn't created it yet)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = subprocess.run(
            ["kubectl", "get", "pod", "-l", label_selector, "-n", namespace, "-o", "name"],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0 and r.stdout.strip():
            return
        time.sleep(5)
    raise RuntimeError(
        f"No pod matching '{label_selector}' appeared within {timeout}s. "
        "Check the PostgresCluster status."
    )


def _wait_pg_primary_ready(namespace: str, timeout: int = 300) -> None:
    """Wait for the postgres primary pod to be ready."""
    print("Waiting for PostgresCluster primary pod to be ready...")
    label_selector = (
        f"postgres-operator.crunchydata.com/cluster={_PG_CLUSTER_NAME},"
        "postgres-operator.crunchydata.com/role=master"
    )
    t0 = time.time()
    _wait_pod_exists(label_selector, namespace, timeout)
    remaining = max(timeout - int(time.time() - t0), 30)
    result = subprocess.run(
        [
            "kubectl",
            "wait",
            "pod",
            "-l",
            label_selector,
            "--for=condition=Ready",
            f"--timeout={remaining}s",
            "-n",
            namespace,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"PostgresCluster primary did not become ready within {timeout}s:\n"
            + (result.stderr or result.stdout)
        )
    print("PostgresCluster primary is ready.")


def _get_secret_value(name: str, key: str, namespace: str) -> str:
    result = subprocess.run(
        [
            "kubectl",
            "get",
            "secret",
            name,
            "-n",
            namespace,
            "-o",
            f"jsonpath={{.data.{key}}}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(
            f"Could not read key '{key}' from secret '{name}': {result.stderr}"
        )
    return base64.b64decode(result.stdout.strip()).decode()


def _create_schema(namespace: str, password: str) -> None:
    """Run a one-shot psql pod to create the required tables."""
    print("Creating database schema via temporary psql pod...")
    host = _PG_HOST_TEMPLATE.format(ns=namespace)
    result = subprocess.run(
        [
            "kubectl",
            "run",
            "pg-schema-init",
            "--rm",
            "-i",
            "--restart=Never",
            f"-n={namespace}",
            "--image=postgres:17",
            f"--env=PGPASSWORD={password}",
            "--",
            "psql",
            "-h",
            host,
            "-U",
            _PG_USER,
            "-d",
            _PG_DB,
        ],
        input=_SCHEMA_SQL,
        text=True,
        capture_output=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Schema creation failed:\n{result.stderr or result.stdout}")
    print("Schema created (or already existed).")


def _wait_isvc_ready(name: str, namespace: str, timeout: int) -> None:
    print(f"Waiting for InferenceService '{name}' (timeout {timeout}s)...")
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


def _internal_isvc_url(name: str, namespace: str) -> str:
    """Return the ISVC's internal address. Unlike hitting the predictor
    Service directly, this routes through the transformer — the component
    that persists requests/responses to Postgres."""
    result = subprocess.run(
        [
            "kubectl",
            "get",
            "inferenceservice",
            name,
            "-n",
            namespace,
            "-o",
            "jsonpath={.status.address.url}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(
            f"Could not read internal address for InferenceService '{name}': "
            f"{result.stderr}"
        )
    return result.stdout.strip()


def _smoke_test(namespace: str, password: str, timeout: int = 120) -> None:
    """POST numeric values to the primary (doubler) ISVC and verify predictions.

    The doubler predictor multiplies each input value by FACTOR=2, so
    [1.0, 2.0, 3.0] must produce predictions [2.0, 4.0, 6.0].
    """
    url = _internal_isvc_url(_DOUBLER_ISVC, namespace) + "/v1/models/model:predict"
    inputs = [1.0, 2.0, 3.0]
    expected = [2.0, 4.0, 6.0]
    payload = json.dumps({"values": inputs}).encode()
    request_id = uuid.uuid4()
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "x-request-id": str(request_id),
                },
                method="POST",
            )
            with urllib.request.urlopen(
                req, timeout=min(15, max(1, deadline - time.monotonic()))
            ) as resp:
                body = json.loads(resp.read())
            predictions = body.get("results")
            if predictions is None:
                raise RuntimeError(f"no 'results' key in response: {body}")
            if predictions != expected:
                raise RuntimeError(
                    f"doubler (FACTOR=2) returned wrong predictions: "
                    f"got {predictions}, expected {expected}"
                )
            break
        except Exception as exc:
            last_err = exc
            time.sleep(min(5, max(0, deadline - time.monotonic())))
    else:
        raise RuntimeError(
            f"Prediction smoke test failed after {timeout}s: {last_err}"
        )
    print(f"Prediction verified for request {request_id}: {inputs} -> {predictions}")

    host = _PG_HOST_TEMPLATE.format(ns=namespace)
    sql = (
        "SELECT "
        "(SELECT COUNT(*) FROM public.inference_requests "
        f"WHERE request_id = UUID '{request_id}') || '|' || "
        "(SELECT COUNT(*) FROM public.inference_response "
        f"WHERE request_id = UUID '{request_id}');"
    )
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(
                f"Persistence smoke test timed out after {timeout}s: request "
                f"{request_id} was not found in both persistence tables."
            )
        try:
            result = subprocess.run(
                [
                    "kubectl",
                    "run",
                    f"pg-smoke-{request_id.hex[:12]}",
                    "--rm",
                    "-i",
                    "--quiet",
                    "--restart=Never",
                    f"-n={namespace}",
                    "--image=postgres:17",
                    f"--env=PGPASSWORD={password}",
                    "--",
                    "psql",
                    "-qAt",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-h",
                    host,
                    "-U",
                    _PG_USER,
                    "-d",
                    _PG_DB,
                    "-c",
                    sql,
                ],
                capture_output=True,
                text=True,
                timeout=remaining,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Persistence smoke test timed out after {timeout}s while querying "
                f"the persistence tables for request {request_id}."
            ) from exc
        if result.returncode != 0:
            raise RuntimeError(
                f"Persistence query failed for request {request_id}:\n"
                + (result.stderr or result.stdout)
            )
        try:
            request_count, response_count = map(
                int, result.stdout.strip().split("|", maxsplit=1)
            )
        except (ValueError, TypeError) as exc:
            raise RuntimeError(
                f"Persistence query returned invalid counts for request {request_id}: "
                f"{result.stdout!r}"
            ) from exc
        if request_count == response_count == 1:
            print(f"Persistence verified for request {request_id}.")
            return
        if request_count > 1 or response_count > 1:
            raise RuntimeError(
                f"Persistence check found {request_count} request row(s) and "
                f"{response_count} response row(s) for request {request_id}; "
                "expected exactly one of each."
            )
        time.sleep(min(5, max(0, deadline - time.monotonic())))


# ── Entry point ───────────────────────────────────────────────────────────────


def deploy(timeout: int = 600) -> None:
    ns = _namespace()

    # 1. Postgres cluster — _kubectl_apply raises with an actionable message on
    #    "no matches for kind" (operator not installed) or Forbidden (RBAC missing).
    with open(os.path.join(_ROOT, "postgres-cluster.yaml")) as fh:
        pg_manifest = fh.read()
    _kubectl_apply(pg_manifest, ns)
    print(f"Applied PostgresCluster '{_PG_CLUSTER_NAME}' in namespace '{ns}'.")

    _wait_pg_primary_ready(ns, timeout=300)
    _wait_for_secret(_PG_SECRET_NAME, ns, timeout=120)

    password = _get_secret_value(_PG_SECRET_NAME, "password", ns)
    _create_schema(ns, password)

    # 2. Both InferenceServices
    for yaml_file in (
        "doubler-inference-service.yaml",
        "tripler-inference-service.yaml",
    ):
        with open(os.path.join(_ROOT, yaml_file)) as fh:
            manifest = fh.read()
        _kubectl_apply(manifest, ns)

    print("Applied doubler and tripler InferenceServices.")

    readiness_deadline = time.monotonic() + timeout
    for isvc_name in (_DOUBLER_ISVC, _TRIPLER_ISVC):
        remaining = readiness_deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(
                f"Combined {timeout}s readiness deadline was exhausted before waiting "
                f"for InferenceService '{isvc_name}'."
            )
        _wait_isvc_ready(isvc_name, ns, max(1, int(remaining)))

    print("Both InferenceServices are ready.")
    print(
        "NOTE: Istio VirtualService manifests (istio/) are not applied in CI — "
        "they require namespace and domain substitution and must be configured manually."
    )

    _smoke_test(ns, password)


if __name__ == "__main__":
    try:
        deploy()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
