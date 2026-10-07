"""Deploy the Markdown Notes MCP server and exercise it through Agent Gateway."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import uuid
from typing import Callable, TypeVar

_NAME = "markdown-notes"
_TOOLS = {"list_notes", "get_note", "save_note", "search_notes", "delete_note"}
_EXAMPLE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MANIFEST = os.path.join(_EXAMPLE_DIR, "markdown-notes.yaml")
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

    federated_tools = {f"{_NAME}_{tool}" for tool in _TOOLS}

    def workspace_session() -> McpSession:
        session = McpSession(workspace_mcp_url(ns))
        missing = federated_tools - set(session.list_tools())
        if missing:
            raise RuntimeError(f"missing tools {sorted(missing)}")
        return session

    session = _retry("Workspace MCP endpoint", workspace_session)
    print(f"Workspace MCP endpoint lists {sorted(federated_tools)}.")

    note = f"ci-smoke-{uuid.uuid4().hex[:8]}"
    token = uuid.uuid4().hex
    session.call_tool(
        f"{_NAME}_save_note", {"name": note, "content": f"# CI smoke\n\n{token}\n"}
    )
    try:
        result = session.call_tool(f"{_NAME}_search_notes", {"query": token})
        hits = [hit["name"] for hit in result["structuredContent"]["result"]]
        if hits != [note]:
            raise RuntimeError(f"search_notes returned {hits}, expected [{note!r}]")
        text = session.call_tool(f"{_NAME}_get_note", {"name": note})["content"][0][
            "text"
        ]
        if token not in text:
            raise RuntimeError(f"get_note returned unexpected content: {text!r}")
    finally:
        session.call_tool(f"{_NAME}_delete_note", {"name": note})
    print("Saved, searched, read, and deleted a note.")

    url = server_mcp_url(ns, _NAME)

    def keyed_session() -> None:
        missing = _TOOLS - set(McpSession(url, api_key=api_key).list_tools())
        if missing:
            raise RuntimeError(f"missing tools {sorted(missing)}")

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
