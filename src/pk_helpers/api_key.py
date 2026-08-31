"""Read an inference API key from the environment or prompt for one."""

from __future__ import annotations

import argparse
import os
import sys
from getpass import getpass

_API_KEY_ENV_VAR = "INFERENCE_SERVICE_API_KEY"


def _key_from_env() -> str | None:
    """Return the admin-provisioned API key from the environment, if set."""
    value = os.environ.get(_API_KEY_ENV_VAR, "").strip()
    return value or None


def get_or_create_api_key() -> str:
    """Return the configured API key, prompting if necessary."""
    env_key = _key_from_env()
    if env_key:
        return env_key

    key = getpass(
        f"${_API_KEY_ENV_VAR} is unset. Please enter your model-serving API "
        "key (ask your cluster admin, or use pkui if available on your "
        "platform): "
    ).strip()
    if not key:
        raise RuntimeError(
            f"No API key available: ${_API_KEY_ENV_VAR} is unset and no key "
            "was entered."
        )
    return key


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
