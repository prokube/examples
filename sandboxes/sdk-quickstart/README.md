# Sandbox SDK Quickstart

This example shows how to use the Python Sandbox SDK from a notebook. It creates or uses a WarmPool, claims a sandbox, runs stateful Python code, executes shell commands, writes and reads files, and cleans up the sandbox.

Use this example to understand the SDK and the core Agent Sandbox features before wiring them into a larger agent or automation workflow. An example that integrates Sandboxes into an agent framework belongs in a separate example directory.

## Files

| File | Purpose |
|---|---|
| `sandbox-sdk-quickstart.ipynb` | Step-by-step notebook for the Python Sandbox SDK. |

## Prerequisites

- A prokube workspace with the Sandbox module enabled.
- A workspace that may create Sandbox WarmPools, or an existing WarmPool such as `python-pool`.
- An API key with Sandbox API access if you run the notebook outside the cluster.

In a managed Lab, this repository is usually available at `~/examples`. Open:

```text
~/examples/sandboxes/sdk-quickstart/sandbox-sdk-quickstart.ipynb
```

## Configuration

The notebook uses these environment variables:

| Variable | Required | Description |
|---|---|---|
| `PROKUBE_API_URL` | Usually | Base URL of pkui for external access, for example `https://<cluster-domain>/pkui`. In a managed Lab, the notebook uses the in-cluster Agent Gateway service. |
| `PROKUBE_WORKSPACE` | Usually | Workspace namespace. In a managed Lab, the notebook can detect it from the mounted service account. |
| `PROKUBE_USER_ID` | Usually | User identity for in-cluster access without an API key. In single-user workspaces, this is commonly the workspace name. |
| `PROKUBE_API_KEY` | For external access | API key with Sandbox API access. In-cluster use can rely on the authenticated workspace identity if configured. |
| `SANDBOX_POOL` | No | WarmPool name. Defaults to `python-pool`. |
| `SANDBOX_IMAGE` | No | Image used when the notebook creates a WarmPool. Defaults to `europe-west3-docker.pkg.dev/prokube-internal/prokube-customer/pk-sandbox-base:v14-05-2026`; override it with an image available in your deployment. |

Do not store real API keys in the notebook. Set them as environment variables or use your notebook environment's secret handling.

For external access with an API key, set these variables before using the SDK:

```python
import os

os.environ["PROKUBE_API_URL"] = "https://<cluster-domain>/pkui"
os.environ["PROKUBE_WORKSPACE"] = "<workspace>"
os.environ["PROKUBE_API_KEY"] = "<api-key>"
```

## What the Notebook Covers

1. Install the recommended Python SDK release.
2. Validate the workspace and SDK configuration.
3. Optionally create a WarmPool with the SDK.
4. Claim a sandbox from a WarmPool.
5. Run stateful Python code with `run_code()`.
6. Run shell commands with `commands.run()`.
7. Write, read, and list files under `/workspace`.
8. Clean up the claimed sandbox with `kill()`.

## Next Step

After this quickstart works, build higher-level agents by wrapping the same operations in your agent runtime. Keep sandbox cleanup explicit, and avoid logging API keys or secret values.
