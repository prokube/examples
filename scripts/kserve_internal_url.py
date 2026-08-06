"""
Resolve the internal in-cluster predict URL for a KServe InferenceService,
compatible with both the currently-released prokube platform and the
upcoming agentgateway-based platform.

Currently-released prokube versions expose the predictor directly as a
plain Kubernetes Service named ``<isvc-name>-predictor`` in the caller's
namespace, using the KServe V1 protocol::

    http://<isvc-name>-predictor.<namespace>.svc.cluster.local/v1/models/<model-name>:predict

Upcoming (not yet released) prokube versions route ALL serving traffic —
internal and external alike — through a shared ``agentgateway-proxy``
Service in the ``agentgateway-system`` namespace::

    http://agentgateway-proxy.agentgateway-system.svc.cluster.local/_platform/serving/<namespace>/<isvc-name>/v2/models/<model-name>/infer

The request/response payload is unchanged between the two (plain KServe V1
JSON, e.g. ``{"instances": [...]}``) — only the URL differs, so callers
don't need to change how they build the request body.

Usage
-----
    import sys, subprocess, os
    _root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
    sys.path.insert(0, os.path.join(_root, "scripts"))
    from kserve_internal_url import internal_predict_url

    url = internal_predict_url(isvc_name, namespace, model_name)
"""

from __future__ import annotations

import socket
from functools import lru_cache

_AGENTGATEWAY_NAMESPACE = "agentgateway-system"
_AGENTGATEWAY_SERVICE = "agentgateway-proxy"
_AGENTGATEWAY_HOST = f"{_AGENTGATEWAY_SERVICE}.{_AGENTGATEWAY_NAMESPACE}.svc.cluster.local"


@lru_cache(maxsize=1)
def _agentgateway_available() -> bool:
    """Return True if the new agentgateway-proxy Service exists in the cluster.

    Uses a plain DNS lookup rather than `kubectl get service`: notebook pod
    service accounts typically lack RBAC to read Services in another
    namespace (e.g. `default-editor` gets a 403 Forbidden on
    `agentgateway-system`), but every Kubernetes Service gets a DNS record
    regardless of RBAC, and a non-existent Service fails resolution outright
    (`socket.gaierror`) rather than returning an HTTP-level error. Cached for
    the lifetime of the process — no need to repeat it for every predict
    call in a run.
    """
    try:
        socket.gethostbyname(_AGENTGATEWAY_HOST)
        return True
    except socket.gaierror:
        return False


def internal_predict_url(isvc_name: str, namespace: str, model_name: str) -> str:
    """Return the internal in-cluster V1-protocol predict URL for an ISVC.

    Detects whether the new agentgateway-proxy is present (upcoming prokube
    release) and returns the matching URL; falls back to hitting the KServe
    predictor Service directly on clusters that don't have it yet. The
    request/response payload format is unchanged either way.
    """
    if _agentgateway_available():
        return (
            f"http://{_AGENTGATEWAY_HOST}"
            f"/_platform/serving/{namespace}/{isvc_name}/v2/models/{model_name}/infer"
        )
    return (
        f"http://{isvc_name}-predictor.{namespace}.svc.cluster.local"
        f"/v1/models/{model_name}:predict"
    )
