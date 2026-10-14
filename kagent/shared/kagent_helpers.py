"""Talk to kagent agents through Agent Gateway and create the examples' prerequisites."""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from getpass import getpass
from pathlib import Path
from typing import Any

_AGENTGATEWAY_HOST = "agentgateway-proxy.agentgateway-system.svc.cluster.local"

_KAGENT_DIR = Path(__file__).resolve().parent.parent
_MODEL_CONFIG = _KAGENT_DIR / "basic-agent" / "anthropic-model.yaml"
_FETCH_SERVER = (
    _KAGENT_DIR.parent
    / "mcp-servers"
    / "deploy-upstream-mcp-server"
    / "fetch-server.yaml"
)
_WEB_RESEARCHER = _KAGENT_DIR / "agent-with-mcp" / "web-researcher.yaml"


def workspace_a2a_url(namespace: str, agent: str) -> str:
    """Return the internal A2A URL of an agent (no API key from inside the cluster)."""
    return f"http://{_AGENTGATEWAY_HOST}/_platform/a2a/{namespace}/{agent}"


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

    Retries HTTP and connection errors within ``timeout`` because Agent Gateway
    and API key scopes pick up a new agent a few seconds after it is ready, and
    prints each failure. A response timeout is not retried, since the agent may
    already be working on the message.
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
        remaining = max(deadline - time.monotonic(), 1)
        try:
            with urllib.request.urlopen(request, timeout=remaining) as resp:
                body = json.loads(resp.read())
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read(300).decode(errors="replace").strip()
            error = f"HTTP {exc.code}: {detail}"
            if exc.code in (401, 403):
                error += " (check that the API key has access to this agent)"
        except urllib.error.URLError as exc:
            error = str(exc.reason)
        if time.monotonic() + 5 >= deadline:
            raise RuntimeError(f"{url} not reachable after {timeout}s: {error}")
        print(f"{error}; retrying in 5s")
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


def _kubectl(*args: str, input: str | None = None) -> str:
    """Run kubectl and return its output.

    Jupyter does not show a subprocess's output, so callers print it.
    """
    result = subprocess.run(
        ["kubectl", *args], input=input, capture_output=True, text=True
    )
    if result.returncode != 0:
        # Only the verb, so that a --from-literal secret value is never shown.
        raise RuntimeError(f"kubectl {args[0]} failed: {result.stderr.strip()}")
    return result.stdout


def ensure_anthropic_secret() -> None:
    """Create the ``anthropic-api-key`` Secret unless it exists.

    Prompts for the key unless ``ANTHROPIC_API_KEY`` is set.
    """
    if _kubectl(
        "get", "secret", "anthropic-api-key", "-o", "name", "--ignore-not-found"
    ):
        print("Using the existing anthropic-api-key Secret.")
        return
    api_key = (
        os.environ.get("ANTHROPIC_API_KEY") or getpass("Anthropic API key: ")
    ).strip()
    if not api_key:
        raise ValueError(
            "No Anthropic API key entered. Run the cell again and paste your key."
        )
    print(
        _kubectl(
            "create",
            "secret",
            "generic",
            "anthropic-api-key",
            f"--from-literal=ANTHROPIC_API_KEY={api_key}",
        ),
        end="",
    )
    # The label lists the Secret under K8s Secrets in the prokube user menu.
    print(
        _kubectl("label", "secret", "anthropic-api-key", "prokube.ai/user-secret=true"),
        end="",
    )


def ensure_model_config() -> None:
    """Apply the ``anthropic-haiku`` ModelConfig from basic-agent and wait until kagent accepts it."""
    print(_kubectl("apply", "-f", str(_MODEL_CONFIG)), end="")
    print(
        _kubectl(
            "wait",
            "--for=condition=Accepted",
            "modelconfigs.kagent.dev/anthropic-haiku",
            "--timeout=2m",
        ),
        end="",
    )


def ensure_fetch_server() -> None:
    """Apply the Fetch MCP server from mcp-servers/deploy-upstream-mcp-server and wait until it is ready."""
    print(_kubectl("apply", "-f", str(_FETCH_SERVER)), end="")
    print(
        _kubectl(
            "wait",
            "--for=condition=Ready",
            "mcpservers.toolhive.stacklok.dev/fetch-example",
            "--timeout=3m",
        ),
        end="",
    )


def ensure_web_researcher() -> None:
    """Apply ``web-researcher`` from agent-with-mcp and wait until it is ready.

    Writes the Fetch tool name that ``gateway-mcp`` uses into the manifest first.
    """
    fetch_tool = gateway_mcp_tool_name("fetch-example", "fetch")
    manifest = _WEB_RESEARCHER.read_text().replace("- fetch\n", f"- {fetch_tool}\n")
    print(_kubectl("apply", "-f", "-", input=manifest), end="")
    print(
        _kubectl(
            "wait",
            "--for=condition=Ready",
            "agents.kagent.dev/web-researcher",
            "--timeout=3m",
        ),
        end="",
    )
