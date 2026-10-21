"""Prompt for missing CI prerequisites when run_all.py runs with --interactive."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from getpass import getpass

_ENV_HINTS = {
    "PROKUBE_DOMAIN": "cluster host name, for example my-cluster.prokube.cloud",
    "INFERENCE_SERVICE_API_KEY": "API key with access to the workspace's model servers",
    "MCP_API_KEY": "API key with access to all MCP servers in the workspace",
    "A2A_API_KEY": "API key with access to all agents in the workspace",
    "ANTHROPIC_API_KEY": "Anthropic API key from the Anthropic Console",
}


def prompt_for_prerequisites(
    env_names: Iterable[str], check_mlflow: Callable[[], tuple[bool, str]]
) -> None:
    """Ask for unset variables and offer to create the MLflow secret.

    Answers only go into this process's environment, which the examples
    inherit. An empty answer leaves a variable unset, so preflight skips the
    examples that need it.
    """
    _prompt_for_env(env_names)
    _offer_mlflow_setup(check_mlflow)
    print()


def _prompt_for_env(env_names: Iterable[str]) -> None:
    # The domain comes first so that the API Keys page can be shown with it.
    for name in sorted(env_names, key=lambda n: (n != "PROKUBE_DOMAIN", n)):
        if os.environ.get(name, "").strip():
            print(f"{name} is already set")
            continue
        prompt = f"{name} ({_ENV_HINTS.get(name, 'leave empty to skip')}): "
        value = (input(prompt) if name == "PROKUBE_DOMAIN" else getpass(prompt)).strip()
        if value:
            os.environ[name] = value
        if name == "PROKUBE_DOMAIN":
            domain = os.environ.get(name, "<your-prokube-domain>")
            print(f"Create API keys at https://{domain}/pkui/ai-gateway/keys")


def _offer_mlflow_setup(check_mlflow: Callable[[], tuple[bool, str]]) -> None:
    ok, reason = check_mlflow()
    if ok:
        print("MLflow credentials are valid")
        return
    print(f"MLflow: {reason}")
    answer = input("Create or replace the mlflow-credentials secret now? [y/N] ")
    if answer.strip().lower() == "y":
        from pk_helpers import setup_mlflow_credentials

        setup_mlflow_credentials(rerun=True)
