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

import subprocess
from functools import lru_cache

_AGENTGATEWAY_NAMESPACE = "agentgateway-system"
_AGENTGATEWAY_SERVICE = "agentgateway-proxy"


@lru_cache(maxsize=1)
def _agentgateway_available() -> bool:
    """Return True if the new agentgateway-proxy Service exists in the cluster.

    Cached for the lifetime of the process — this is a cheap probe, but
    there's no need to repeat it for every predict call in a run.
    """
    result = subprocess.run(
        [
            "kubectl",
            "get",
            "service",
            _AGENTGATEWAY_SERVICE,
            "-n",
            _AGENTGATEWAY_NAMESPACE,
            "--ignore-not-found",
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def internal_predict_url(isvc_name: str, namespace: str, model_name: str) -> str:
    """Return the internal in-cluster V1-protocol predict URL for an ISVC.

    Detects whether the new agentgateway-proxy is present (upcoming prokube
    release) and returns the matching URL; falls back to hitting the KServe
    predictor Service directly on clusters that don't have it yet. The
    request/response payload format is unchanged either way.
    """
    if _agentgateway_available():
        return (
            f"http://{_AGENTGATEWAY_SERVICE}.{_AGENTGATEWAY_NAMESPACE}.svc.cluster.local"
            f"/_platform/serving/{namespace}/{isvc_name}/v2/models/{model_name}/infer"
        )
    return (
        f"http://{isvc_name}-predictor.{namespace}.svc.cluster.local"
        f"/v1/models/{model_name}:predict"
    )
