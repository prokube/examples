"""Pre-flight checks: CI dependencies, pk_helpers, MLflow credentials, API key."""

from __future__ import annotations

import os
import re
import subprocess
import sys

from .registry import EXAMPLES, REPO_ROOT
from .results import Result


def require_ci_dependencies() -> None:
    """Fail before starting work if the CI-only dependencies are unavailable."""
    try:
        import papermill  # noqa: F401
        from kfp.client import Client  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "CI dependencies are missing. Install them with "
            f'`python -m pip install -e "{REPO_ROOT}[ci]"`.'
        ) from exc


def ensure_pk_helpers() -> None:
    """Editable-install the pk_helpers package if it is not importable.

    Notebooks and serving apply.py scripts import shared prokube helpers via
    ``from pk_helpers import ...``. Installing the repo editable makes the same
    interpreter used by the CI subprocesses able to resolve those imports.
    """
    try:
        import pk_helpers  # noqa: F401
    except ImportError:
        print("pk_helpers not found — installing repo editable...")
        # --user outside a virtualenv (e.g. in a Kubeflow notebook pod) so the
        # install lands under the persistent $HOME/.local instead of the
        # container image's site-packages, which is wiped on the next pod
        # restart. pip rejects --user inside a virtualenv, hence the guard.
        user_flag = [] if sys.prefix != sys.base_prefix else ["--user"]
        subprocess.run(
            [sys.executable, "-m", "pip", "install", *user_flag, "-e", str(REPO_ROOT)],
            check=True,
        )
        print("pk_helpers installed.")


def namespace() -> str:
    with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace") as fh:
        return fh.read().strip()


def check_mlflow_credentials() -> tuple[bool, str]:
    """Return (ok, reason). Checks secret existence then validates with MLflow API."""
    import base64 as _b64
    import json as _json
    import urllib.error
    import urllib.request

    ns = namespace()
    r = subprocess.run(
        ["kubectl", "get", "secret", "mlflow-credentials", "-n", ns, "-o", "json"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return False, (
            "mlflow-credentials secret not found — run the interactive "
            "credential setup cell first"
        )
    try:
        data = _json.loads(r.stdout)["data"]
        uri = _b64.b64decode(data["MLFLOW_TRACKING_URI"]).decode().rstrip("/")
        username = _b64.b64decode(data["MLFLOW_TRACKING_USERNAME"]).decode()
        password = _b64.b64decode(data["MLFLOW_TRACKING_PASSWORD"]).decode()
    except KeyError as exc:
        return (
            False,
            f"mlflow-credentials secret is missing key {exc} — re-run the "
            "interactive credential setup cell",
        )

    if not re.match(r"^https?://", uri):
        return (
            False,
            f"mlflow-credentials secret has a malformed MLFLOW_TRACKING_URI "
            f"({uri!r}) — re-run the interactive credential setup cell and "
            "enter the full https://<domain>/mlflow URL",
        )

    creds = _b64.b64encode(f"{username}:{password}".encode()).decode()
    try:
        req = urllib.request.Request(
            f"{uri}/api/2.0/mlflow/experiments/search?max_results=1",
            headers={"Authorization": f"Basic {creds}"},
        )
        urllib.request.urlopen(req, timeout=8)
        return True, "OK"
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return False, (
                "MLflow credentials are invalid or the PAT has expired — "
                "re-run the interactive credential setup cell"
            )
        return (
            False,
            f"MLflow API returned HTTP {exc.code} — check MLFLOW_TRACKING_URI in the secret",
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"Could not reach MLflow at {uri}: {exc}"


def check_kserve_api_key() -> tuple[bool, str]:
    """Check that headless CI has an inference API key."""
    if os.environ.get("INFERENCE_SERVICE_API_KEY", "").strip():
        return True, "OK"
    return False, (
        "INFERENCE_SERVICE_API_KEY is unset — export a model-serving API key "
        "(ask your cluster admin, or use pkui if available) before running CI"
    )


def check_credentials() -> tuple[bool, str, bool, str]:
    """Run the MLflow and kserve API key checks, printing their outcome.

    Returns (mlflow_ok, mlflow_reason, api_key_ok, api_key_reason). Shared by
    `preflight` (real runs) and `--dry-run` so contributors can see what
    would be skipped before committing to a full run.
    """
    print("Pre-flight: checking MLflow credentials...")
    mlflow_ok, mlflow_reason = check_mlflow_credentials()
    if mlflow_ok:
        print("  [OK] MLflow credentials valid")
    else:
        print(f"  [SKIP] {mlflow_reason}")

    print("Pre-flight: checking kserve API key...")
    api_key_ok, api_key_reason = check_kserve_api_key()
    if api_key_ok:
        print("  [OK] INFERENCE_SERVICE_API_KEY is set")
    else:
        print(f"  [SKIP] {api_key_reason}")

    return mlflow_ok, mlflow_reason, api_key_ok, api_key_reason


def preflight(results: dict[str, Result]) -> bool:
    """Validate CI dependencies, MLflow credentials, and the kserve API key.

    MLflow-dependent and API-key-dependent examples are recorded as SKIP in
    `results` on failure. Returns True if MLflow credentials are valid.
    """
    require_ci_dependencies()
    ensure_pk_helpers()

    mlflow_ok, mlflow_reason, api_key_ok, api_key_reason = check_credentials()

    if not mlflow_ok:
        for ex in EXAMPLES:
            if ex.mlflow_dependent:
                results[ex.name] = Result(
                    name=ex.name, status="SKIP", error=mlflow_reason
                )

    if not api_key_ok:
        for ex in EXAMPLES:
            if ex.api_key_dependent and ex.name not in results:
                results[ex.name] = Result(
                    name=ex.name, status="SKIP", error=api_key_reason
                )

    return mlflow_ok
