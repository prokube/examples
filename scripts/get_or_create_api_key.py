"""
Utility to obtain a prokube model-serving API key for use in examples.

Usage from a notebook
---------------------
    import sys, subprocess, os
    _root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
    sys.path.insert(0, os.path.join(_root, "scripts"))
    from get_or_create_api_key import get_or_create_api_key

    API_KEY = get_or_create_api_key()

CLI usage
---------
    python get_or_create_api_key.py
    # prints the key to stdout

Resolution order
----------------
There is no automated way to provision a model-serving API key from within a
notebook or script.  This helper only looks for a key that has already been
made available in the environment, and otherwise prompts for one:

1. **Environment variable.**  If an admin has pre-provisioned a key and
   injected it into the notebook pod via the ``INFERENCE_SERVICE_API_KEY``
   environment variable, that value is used.

2. **Interactive prompt.**  Otherwise, the caller is prompted to paste a key.
   Obtain a key from your cluster administrator, or via the prokube UI
   (``pkui``) if it is available on your platform.
"""

from __future__ import annotations

import argparse
import os
import sys
from getpass import getpass

# Env var an admin injects into the notebook pod with a pre-provisioned
# model-serving API key.
_API_KEY_ENV_VAR = "INFERENCE_SERVICE_API_KEY"


def _key_from_env() -> str | None:
    """Return the admin-provisioned API key from the environment, if set."""
    value = os.environ.get(_API_KEY_ENV_VAR, "").strip()
    return value or None


def get_or_create_api_key() -> str:
    """Return a model-serving API key.

    See the module docstring for the resolution order: the
    ``INFERENCE_SERVICE_API_KEY`` env var if set, otherwise an interactive
    prompt.
    """
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


if __name__ == "__main__":
    try:
        argparser = argparse.ArgumentParser(
            description="Get a prokube model-serving API key"
        )
        argparser.parse_args()
        print(get_or_create_api_key())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
