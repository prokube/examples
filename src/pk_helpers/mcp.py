"""Minimal MCP Streamable HTTP client for the Agent Gateway MCP routes."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

_AGENTGATEWAY_HOST = "agentgateway-proxy.agentgateway-system.svc.cluster.local"
_PROTOCOL_VERSION = "2025-03-26"


def workspace_mcp_url(namespace: str) -> str:
    """Return the internal federated MCP endpoint of a workspace (no API key)."""
    return f"http://{_AGENTGATEWAY_HOST}/_platform/mcp/{namespace}"


def server_mcp_url(namespace: str, server: str) -> str:
    """Return the in-cluster URL of a server's API-key route.

    This is the route that ``https://<domain>/svc/mcp/<namespace>/<server>``
    serves externally, so it enforces the same API key policy.
    """
    return f"http://{_AGENTGATEWAY_HOST}/svc/mcp/{namespace}/{server}"


class McpSession:
    """An initialized MCP session; requests are sent one at a time."""

    def __init__(self, url: str, api_key: str | None = None, timeout: int = 30):
        self.url = url
        self.timeout = timeout
        self._headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self._next_id = 1

        init = self.request(
            "initialize",
            {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "pk-helpers", "version": "1.0"},
            },
        )
        self.server_info: dict[str, Any] = init.get("serverInfo", {})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _post(self, payload: dict[str, Any]) -> str:
        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode(),
            headers=self._headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            session_id = resp.headers.get("Mcp-Session-Id")
            if session_id:
                self._headers["Mcp-Session-Id"] = session_id
            return resp.read().decode()

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Send a JSON-RPC request and return its ``result``."""
        request_id = self._next_id
        self._next_id += 1
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        body = self._post(payload)

        # Responses arrive either as plain JSON or as server-sent events.
        lines = [
            line.removeprefix("data:").strip()
            for line in body.splitlines()
            if line.startswith("data:")
        ] or [body]
        for line in lines:
            message = json.loads(line)
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(f"MCP {method} failed: {message['error']}")
            return message["result"]
        raise RuntimeError(f"MCP {method}: no response in {body[:500]!r}")

    def list_tools(self) -> list[str]:
        return [tool["name"] for tool in self.request("tools/list")["tools"]]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool and return its result; raise when the tool reports an error."""
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise RuntimeError(f"Tool {name} failed: {result.get('content')}")
        return result


def connect_when_ready(
    url: str, api_key: str | None = None, tool_prefix: str = "", timeout: int = 180
) -> McpSession:
    """Open a session once the endpoint lists a tool starting with ``tool_prefix``.

    Agent Gateway picks up a new MCP server a few seconds after it is ready.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            session = McpSession(url, api_key=api_key)
            if any(name.startswith(tool_prefix) for name in session.list_tools()):
                return session
            error = f"no tools starting with {tool_prefix!r}"
        except urllib.error.HTTPError as exc:
            error = str(exc)
            if exc.code in (401, 403):
                error += " (check that the API key has access to this MCP server)"
        except urllib.error.URLError as exc:
            error = str(exc)
        if time.monotonic() >= deadline:
            raise RuntimeError(f"{url} not ready after {timeout}s: {error}")
        time.sleep(5)
