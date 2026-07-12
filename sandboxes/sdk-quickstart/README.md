# Sandbox SDK Quickstart

This example shows how to use the Python Sandbox SDK from a notebook. It claims a sandbox from a WarmPool, runs stateful Python code, executes shell commands, writes and reads files, and cleans up the sandbox.

Use this example when you want to verify that your workspace can drive Agent Sandboxes programmatically before building a larger agent or automation workflow.

## Files

| File | Purpose |
|---|---|
| `sandbox-sdk-quickstart.ipynb` | Step-by-step notebook for the Python Sandbox SDK. |

## Prerequisites

- A prokube workspace with the Sandbox module enabled.
- A ready WarmPool in the workspace, for example `python-pool`.
- An API key with Sandbox API access if you run the notebook outside the cluster.

In a managed Lab, this repository is usually available at `~/examples`. Open:

```text
~/examples/sandboxes/sdk-quickstart/sandbox-sdk-quickstart.ipynb
```

## Configuration

The notebook uses these environment variables:

| Variable | Required | Description |
|---|---|---|
| `PROKUBE_API_URL` | Yes | Base URL of pkui, including the path prefix, for example `https://<cluster-domain>/pkui`. |
| `PROKUBE_WORKSPACE` | Usually | Workspace namespace. In a managed Lab, the notebook can detect it from the mounted service account. |
| `PROKUBE_API_KEY` | For external access | API key with Sandbox API access. In-cluster use can rely on the authenticated workspace identity if configured. |
| `SANDBOX_POOL` | No | WarmPool name. Defaults to `python-pool`. |

Do not store real API keys in the notebook. Set them as environment variables or use your notebook environment's secret handling.

## What the Notebook Covers

1. Install the recommended Python SDK release.
2. Validate the workspace and SDK configuration.
3. Claim a sandbox from a WarmPool.
4. Run stateful Python code with `run_code()`.
5. Run shell commands with `commands.run()`.
6. Write, read, and list files under `/workspace`.
7. Clean up the claimed sandbox with `kill()`.

## Next Step

After this quickstart works, build higher-level agents by wrapping the same operations in your agent runtime. Keep sandbox cleanup explicit, and avoid logging API keys or secret values.
