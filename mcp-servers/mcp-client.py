#!/usr/bin/env python3
"""Minimal Streamable HTTP client for the prokube MCP examples."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


PROTOCOL_VERSION = "2024-11-05"


def _parse_response(payload: bytes, request_id: int) -> dict[str, Any]:
    text = payload.decode("utf-8", errors="replace")
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        decoded = None
    candidates: list[Any] = [decoded] if decoded is not None else []
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        line = line[5:].strip()
        if not line:
            continue
        try:
            candidates.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate.get("id") == request_id:
            return candidate
    raise RuntimeError(f"MCP response did not contain request id {request_id}")


class McpClient:
    def __init__(self, endpoint: str, api_key: str | None, auth: str) -> None:
        self.endpoint = endpoint
        self.session_id: str | None = None
        self.headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if api_key:
            if auth == "bearer":
                self.headers["Authorization"] = f"Bearer {api_key}"
            else:
                self.headers["x-api-key"] = api_key

    def _post(
        self, message: dict[str, Any], request_id: int | None = None
    ) -> dict[str, Any] | None:
        headers = dict(self.headers)
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
            headers["MCP-Protocol-Version"] = PROTOCOL_VERSION
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(message).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            session_id = response.headers.get("Mcp-Session-Id")
            if session_id:
                self.session_id = session_id
            payload = response.read(1_000_001)
        if len(payload) > 1_000_000:
            raise RuntimeError("MCP response exceeded 1 MB")
        if request_id is None:
            return None
        return _parse_response(payload, request_id)

    def initialize(self) -> None:
        response = self._post(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {
                        "name": "prokube-examples",
                        "version": "1.0",
                    },
                },
            },
            request_id=1,
        )
        if response is None or not isinstance(response.get("result"), dict):
            raise RuntimeError("MCP initialize did not return a result")
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        response = self._post(
            {"jsonrpc": "2.0", "id": 2, "method": method, "params": params},
            request_id=2,
        )
        if response is None:
            raise RuntimeError(f"MCP {method} did not return a response")
        if "error" in response:
            raise RuntimeError(json.dumps(response["error"]))
        result = response.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(f"MCP {method} returned a malformed result")
        return result


def _arguments(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("arguments must be a JSON object")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("endpoint", help="MCP Streamable HTTP endpoint")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="list available tools")
    call = commands.add_parser("call", help="call one tool")
    call.add_argument("tool", help="tool name")
    call.add_argument("--arguments", type=_arguments, default={}, help="JSON object")
    return parser


def main() -> int:
    args = _parser().parse_args()
    auth = os.environ.get("MCP_AUTH", "bearer").lower()
    if auth not in {"bearer", "x-api-key"}:
        print("MCP_AUTH must be 'bearer' or 'x-api-key'", file=sys.stderr)
        return 2
    client = McpClient(args.endpoint, os.environ.get("MCP_API_KEY"), auth)
    try:
        client.initialize()
        if args.command == "list":
            result = client.request("tools/list", {})
        else:
            result = client.request(
                "tools/call", {"name": args.tool, "arguments": args.arguments}
            )
    except urllib.error.HTTPError as exc:
        print(f"MCP request failed with HTTP {exc.code}", file=sys.stderr)
        return 1
    except (OSError, RuntimeError) as exc:
        print(f"MCP request failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
