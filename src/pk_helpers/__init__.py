"""Prokube platform helpers shared across the Kubeflow examples.

These utilities abstract away logic specific to the prokube platform so that
notebooks and ``apply.py`` scripts can import them directly instead of wiring
up ``sys.path`` by hand.

Install once (editable) from the repo root::

    pip install -e .

Then import what you need::

    from pk_helpers import get_or_create_api_key, internal_predict_url
"""

from __future__ import annotations

from pk_helpers.api_key import (
    get_or_create_a2a_api_key,
    get_or_create_anthropic_api_key,
    get_or_create_api_key,
    get_or_create_mcp_api_key,
)
from pk_helpers.kagent import (
    agent_a2a_url,
    gateway_mcp_tool_name,
    send_message,
    workspace_a2a_url,
)
from pk_helpers.kserve_url import external_predict_url, internal_predict_url
from pk_helpers.mcp import (
    McpSession,
    connect_when_ready,
    server_mcp_url,
    workspace_mcp_url,
)
from pk_helpers.mlflow_credentials import (
    load_mlflow_credentials,
    require_mlflow_secret,
    setup_mlflow_credentials,
)

__all__ = [
    "McpSession",
    "agent_a2a_url",
    "connect_when_ready",
    "external_predict_url",
    "gateway_mcp_tool_name",
    "get_or_create_a2a_api_key",
    "get_or_create_anthropic_api_key",
    "get_or_create_api_key",
    "get_or_create_mcp_api_key",
    "internal_predict_url",
    "load_mlflow_credentials",
    "require_mlflow_secret",
    "send_message",
    "server_mcp_url",
    "setup_mlflow_credentials",
    "workspace_a2a_url",
    "workspace_mcp_url",
]
