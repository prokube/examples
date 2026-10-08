"""Talk to kagent agents through Agent Gateway and inspect workspace MCP tools."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

_AGENTGATEWAY_HOST = "agentgateway-proxy.agentgateway-system.svc.cluster.local"


def workspace_a2a_url(namespace: str, agent: str) -> str:
    """Return the internal A2A URL of an agent (no API key from inside the cluster)."""
    return f"http://{_AGENTGATEWAY_HOST}/_platform/a2a/{namespace}/{agent}"


def agent_a2a_url(namespace: str, agent: str) -> str:
    """Return the in-cluster URL of an agent's API-key route.

    This is the route that ``https://<domain>/svc/a2a/<namespace>/<agent>``
    serves externally, so it enforces the same API key policy.
    """
    return f"http://{_AGENTGATEWAY_HOST}/svc/a2a/{namespace}/{agent}"


def _response_text(result: dict[str, Any]) -> str:
    if result.get("status", {}).get("state") == "failed":
        raise RuntimeError(f"Agent task failed: {result['status']}")
    parts = [p for a in result.get("artifacts", []) for p in a.get("parts", [])]
    if not parts:
        message = result.get("status", {}).get("message") or result
        parts = message.get("parts", [])
    text = "\n".join(p["text"] for p in parts if p.get("kind") == "text")
    if not text:
        raise RuntimeError(f"Agent returned no text: {result}")
    return text


def send_message(
    url: str, text: str, api_key: str | None = None, timeout: int = 300
) -> str:
    """Send one A2A message and return the agent's text answer.

    Retries HTTP errors until ``timeout`` because Agent Gateway and API key
    scopes pick up a new agent a few seconds after it is ready.
    """
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": text}],
                    "messageId": uuid.uuid4().hex,
                }
            },
        }
    ).encode()

    deadline = time.monotonic() + timeout
    while True:
        request = urllib.request.Request(url, data=payload, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=180) as resp:
                body = json.loads(resp.read())
            break
        except urllib.error.HTTPError as exc:
            error = str(exc)
            if exc.code in (401, 403):
                error += " (check that the API key has access to this agent)"
        except urllib.error.URLError as exc:
            error = str(exc)
        if time.monotonic() >= deadline:
            raise RuntimeError(f"{url} not reachable after {timeout}s: {error}")
        time.sleep(5)

    if "error" in body:
        raise RuntimeError(f"A2A request failed: {body['error']}")
    return _response_text(body["result"])


def gateway_mcp_tool_name(server: str, tool: str, timeout: int = 180) -> str:
    """Return the name kagent's ``gateway-mcp`` uses for a server's tool.

    Agent Gateway prefixes tool names with the server name only when the
    workspace has more than one MCP server.
    """
    candidates = (tool, f"{server}_{tool}")
    deadline = time.monotonic() + timeout
    while True:
        result = subprocess.run(
            [
                "kubectl",
                "get",
                "remotemcpservers.kagent.dev",
                "gateway-mcp",
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            status = json.loads(result.stdout).get("status", {})
            names = [t["name"] for t in status.get("discoveredTools") or []]
            for name in candidates:
                if name in names:
                    return name
            error = f"discovered tools: {names}"
        else:
            error = result.stderr.strip()
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"gateway-mcp did not discover {' or '.join(candidates)} "
                f"after {timeout}s ({error})"
            )
        time.sleep(5)
