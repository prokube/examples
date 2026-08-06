"""Build an internal KServe prediction URL for the available routing mode."""

from __future__ import annotations

import socket
from functools import lru_cache

_AGENTGATEWAY_NAMESPACE = "agentgateway-system"
_AGENTGATEWAY_SERVICE = "agentgateway-proxy"
_AGENTGATEWAY_HOST = f"{_AGENTGATEWAY_SERVICE}.{_AGENTGATEWAY_NAMESPACE}.svc.cluster.local"


@lru_cache(maxsize=1)
def _agentgateway_available() -> bool:
    """Return whether agentgateway resolves through cluster DNS."""
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
            f"/_platform/serving/{namespace}/{isvc_name}/v2/models/{model_name}/infer"
        )
    return (
        f"http://{isvc_name}-predictor.{namespace}.svc.cluster.local"
        f"/v1/models/{model_name}:predict"
    )
