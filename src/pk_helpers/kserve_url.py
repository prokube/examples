"""Build KServe prediction URLs for legacy and Agent Gateway clusters."""

from __future__ import annotations

import socket
from functools import lru_cache

_AGENTGATEWAY_NAMESPACE = "agentgateway-system"
_AGENTGATEWAY_SERVICE = "agentgateway-proxy"
_AGENTGATEWAY_HOST = f"{_AGENTGATEWAY_SERVICE}.{_AGENTGATEWAY_NAMESPACE}.svc.cluster.local"


@lru_cache(maxsize=1)
def _agentgateway_available() -> bool:
    """Return whether Agent Gateway resolves through cluster DNS."""
    try:
        socket.gethostbyname(_AGENTGATEWAY_HOST)
        return True
    except socket.gaierror:
        return False


def internal_predict_url(isvc_name: str, namespace: str, model_name: str) -> str:
    """Return the prediction URL for the detected in-cluster route."""
    if _agentgateway_available():
        return (
            f"http://{_AGENTGATEWAY_HOST}"
            f"/_platform/serving/{namespace}/{isvc_name}/v1/models/{model_name}:predict"
        )
    return (
        f"http://{isvc_name}-predictor.{namespace}.svc.cluster.local"
        f"/v1/models/{model_name}:predict"
    )


def external_predict_url(isvc_url: str, model_name: str, protocol: str = "v1") -> str:
    """Return the external predict URL for the detected cluster generation."""
    suffix = (
        f"/v2/models/{model_name}/infer"
        if protocol == "v2"
        else f"/v1/models/{model_name}:predict"
    )
    if _agentgateway_available() and "/serving/" in isvc_url:
        scheme_host, path = isvc_url.split("/serving/", 1)
        return f"{scheme_host}/svc/serving/{path}{suffix}"
    return f"{isvc_url}{suffix}"
