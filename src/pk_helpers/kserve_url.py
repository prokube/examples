"""Build KServe prediction URLs for Agent Gateway, the only supported route."""

from __future__ import annotations

_AGENTGATEWAY_NAMESPACE = "agentgateway-system"
_AGENTGATEWAY_SERVICE = "agentgateway-proxy"
_AGENTGATEWAY_HOST = f"{_AGENTGATEWAY_SERVICE}.{_AGENTGATEWAY_NAMESPACE}.svc.cluster.local"


def internal_predict_url(isvc_name: str, namespace: str, model_name: str) -> str:
    """Return the in-cluster predict URL, routed through Agent Gateway."""
    return (
        f"http://{_AGENTGATEWAY_HOST}"
        f"/_platform/serving/{namespace}/{isvc_name}/v1/models/{model_name}:predict"
    )


def external_predict_url(isvc_url: str, model_name: str, protocol: str = "v1") -> list[str]:
    """Return candidate external predict URLs for an ISVC's `.status.url`,
    most likely to work first.

    Agent Gateway routes external serving traffic through a `/svc` prefix
    (e.g. `https://<domain>/svc/serving/<ns>/<isvc>/...`) -- `.status.url`
    alone 404s with "route not found". But that `/svc` route only exists if
    `aiGateway.controller.enabled=true` created it; when it's disabled,
    `.status.url` itself is the one that works instead. There's no way to
    detect the controller's enabled-state from inside a pod, so callers
    should try these in order and fall back to the next on a 404.
    """
    suffix = (
        f"/v2/models/{model_name}/infer"
        if protocol == "v2"
        else f"/v1/models/{model_name}:predict"
    )
    urls = [f"{isvc_url}{suffix}"]
    if "/serving/" in isvc_url:
        scheme_host, path = isvc_url.split("/serving/", 1)
        urls.insert(0, f"{scheme_host}/svc/serving/{path}{suffix}")
    return urls
