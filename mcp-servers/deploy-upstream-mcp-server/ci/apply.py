"""Deploy the Fetch MCP server and exercise it through Agent Gateway."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
from typing import Callable, TypeVar

_NAME = "fetch"
_EXAMPLE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MANIFEST = os.path.join(_EXAMPLE_DIR, "fetch-server.yaml")
_REPO_ROOT = os.path.abspath(os.path.join(_EXAMPLE_DIR, "..", ".."))

T = TypeVar("T")


def _namespace() -> str:
    with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace") as fh:
        return fh.read().strip()


def _ensure_pk_helpers() -> None:
    """Editable-install pk_helpers if it isn't importable, so the script runs standalone."""
    try:
        import pk_helpers  # noqa: F401
    except ImportError:
        # --user outside a virtualenv keeps the install under the persistent
        # $HOME/.local of a notebook pod; pip rejects --user inside a venv.
        user_flag = [] if sys.prefix != sys.base_prefix else ["--user"]
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "-q",
                *user_flag,
                "-e",
                _REPO_ROOT,
            ],
            check=True,
        )
        # The editable .pth file is only read at interpreter startup.
        sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))


def _kubectl(*args: str) -> str:
    result = subprocess.run(["kubectl", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    return result.stdout.strip()


def _retry(what: str, fn: Callable[[], T], timeout: int = 180) -> T:
    """Call fn until it succeeds; Agent Gateway picks up new servers asynchronously."""
    deadline = time.time() + timeout
    while True:
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            if time.time() >= deadline:
                raise RuntimeError(f"{what} not ready after {timeout}s: {exc}") from exc
            time.sleep(5)


def deploy_and_test(timeout: int = 300) -> None:
    _ensure_pk_helpers()
    from pk_helpers import (
        McpSession,
        get_or_create_mcp_api_key,
        server_mcp_url,
        workspace_mcp_url,
    )

    api_key = get_or_create_mcp_api_key()  # fail fast, before mutating the cluster
    ns = _namespace()

    print(_kubectl("apply", "-n", ns, "-f", _MANIFEST))
    print(f"Waiting for MCPServer '{_NAME}' to become ready (timeout {timeout}s)...")
    _kubectl(
        "wait",
        "-n",
        ns,
        "--for=condition=Ready",
        f"mcpservers.toolhive.stacklok.dev/{_NAME}",
        f"--timeout={timeout}s",
    )

    def workspace_session() -> McpSession:
        session = McpSession(workspace_mcp_url(ns))
        if "fetch_fetch" not in session.list_tools():
            raise RuntimeError("missing tool 'fetch_fetch'")
        return session

    session = _retry("Workspace MCP endpoint", workspace_session)
    result = session.call_tool("fetch_fetch", {"url": "https://example.com"})
    text = result["content"][0]["text"]
    if not text.strip():
        raise RuntimeError("fetch_fetch returned an empty page")
    print(f"fetch_fetch returned: {text[:80]!r}")

    url = server_mcp_url(ns, _NAME)

    def keyed_session() -> None:
        if "fetch" not in McpSession(url, api_key=api_key).list_tools():
            raise RuntimeError("missing tool 'fetch'")

    _retry(
        f"API key route {url} (check that MCP_API_KEY covers '{_NAME}')", keyed_session
    )
    try:
        McpSession(url)
    except urllib.error.HTTPError as exc:
        if exc.code not in (401, 403):
            raise
    else:
        raise RuntimeError(f"{url} accepted a request without an API key")
    print("API key route accepts MCP_API_KEY and rejects requests without a key.")


if __name__ == "__main__":
    try:
        deploy_and_test()
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        sys.exit(1)
