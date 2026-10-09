"""Read inference and MCP API keys from the environment or prompt for one."""

from __future__ import annotations

import argparse
import os
import sys
from getpass import getpass

_API_KEY_ENV_VAR = "INFERENCE_SERVICE_API_KEY"
_MCP_API_KEY_ENV_VAR = "MCP_API_KEY"


def _key_from_env(env_var: str) -> str | None:
    """Return the admin-provisioned API key from the environment, if set."""
    value = os.environ.get(env_var, "").strip()
    return value or None


def _get_or_prompt(env_var: str, description: str) -> str:
    env_key = _key_from_env(env_var)
    if env_key:
        return env_key

    try:
        key = getpass(
            f"${env_var} is unset. Please enter your {description} (ask your "
            "cluster admin, or use pkui if available on your platform): "
        ).strip()
    except EOFError:
        key = ""
    if not key:
        raise RuntimeError(
            f"No API key available: ${env_var} is unset and no key was entered."
        )
    return key


def get_or_create_api_key() -> str:
    """Return the configured model-serving API key, prompting if necessary."""
    return _get_or_prompt(_API_KEY_ENV_VAR, "model-serving API key")


def get_or_create_mcp_api_key() -> str:
    """Return the configured MCP API key, prompting if necessary."""
    return _get_or_prompt(_MCP_API_KEY_ENV_VAR, "MCP API key")


def main() -> None:
    """Console-script entry point: print the resolved API key."""
    try:
        argparser = argparse.ArgumentParser(
            description="Get a prokube model-serving API key"
        )
        argparser.parse_args()
        print(get_or_create_api_key())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
