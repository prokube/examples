# Pydantic AI Code Agent with Agent Sandboxes

This example shows how to use Agent Sandboxes as tools in a lightweight Python agent built with [Pydantic AI](https://ai.pydantic.dev/).

Use this example when you want an agent framework to run code, execute shell commands, and read or write files in an isolated prokube Sandbox instead of on the user's machine.

## What This Example Shows

- Claiming a sandbox from a WarmPool.
- Exposing sandbox operations as Pydantic AI tools.
- Running Python code in a stateful sandbox kernel.
- Running shell commands inside the sandbox.
- Reading and writing files under `/workspace`.
- Cleaning up the sandbox after the agent run.

This example focuses on agent-framework integration. For a step-by-step SDK walkthrough, see `sandboxes/sdk-quickstart`.

## Files

| File | Purpose |
|---|---|
| `agent.py` | Pydantic AI agent with Sandbox-backed tools. |
| `requirements.txt` | Python dependencies for the example. |

## Prerequisites

- A prokube workspace with the Sandbox module enabled.
- A ready WarmPool, for example `sandbox-sdk-quickstart`.
- Access to an OpenAI-compatible model supported by Pydantic AI.

In a managed Lab, this repository is usually available at `~/examples`. Run the example from its directory:

```bash
cd ~/examples/sandboxes/pydantic-ai-code-agent
pip install -r requirements.txt
```

## Configuration

For the Sandbox SDK in a managed Lab:

```bash
export PROKUBE_API_URL="http://agentgateway-proxy.agentgateway-system.svc.cluster.local"
export PROKUBE_WORKSPACE="<workspace>"
export PROKUBE_USER_ID="<user-or-workspace>"
export SANDBOX_POOL="sandbox-sdk-quickstart"
```

For external access, use an API key instead of `PROKUBE_USER_ID`:

```bash
export PROKUBE_API_URL="https://<cluster-domain>/pkui"
export PROKUBE_WORKSPACE="<workspace>"
export PROKUBE_API_KEY="<api-key>"
export SANDBOX_POOL="sandbox-sdk-quickstart"
```

For the agent model:

```bash
export OPENAI_API_KEY="<model-api-key>"
export OPENAI_BASE_URL="<optional-openai-compatible-base-url>"
export PYDANTIC_AI_MODEL="openai:gpt-4o-mini"
```

Do not store real API keys in source code, notebooks, screenshots, tickets, or chat messages.

## Run

```bash
python agent.py
```

You can pass a custom task:

```bash
python agent.py "Create a CSV with five rows, analyze it, and write a short markdown report."
```

The default task asks the agent to create `/workspace/scores.csv`, analyze it, and write `/workspace/report.md`.

## Safety Notes

The LLM can decide to call tools that run code or shell commands. Use a sandbox image and workspace policy appropriate for the data and dependencies you expose. Keep cleanup explicit, and do not pass secrets to the agent unless the task requires them.
