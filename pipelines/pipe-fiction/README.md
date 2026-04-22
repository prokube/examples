# KFP Pipeline Development & Debugging Demo

This repository demonstrates **advanced development and debugging techniques** for Kubeflow Pipelines (KFP), enabling developers to build, test, and debug ML pipelines efficiently across different environments.

**Note:** This demo uses intentionally simple examples to clearly illustrate the core concepts and debugging workflows. The techniques shown here should also apply to complex ML workloads.

## Overview

As part of our MLOps platform, we support KFP for orchestrating machine learning workflows. This demo showcases:

- **Local Development** with immediate feedback loops
- **Interactive Debugging** with full IDE integration
- **Best Practices** for pipeline development and code organization

## Why?

KFP pipelines are hard to develop and debug - here we try to tackle both challenges.

### The KFP Lightweight Component Challenge

KFP Lightweight Components are easier to use than container components. However, they are designed to be **self-contained** - meaning all code must be either:
- Defined inline within the component function
- Installed via `packages_to_install` parameter

This creates a problem: code duplication. If you need the same utility function in multiple components, you typically have to copy-paste the code into each component, leading to maintenance nightmares, which is the reason most people use container components for heavy lifting.

Alternative approaches like publishing packages to PyPI or private registries are possible, but create their own challenges - you'd need to publish and version your package for every code change during development, which is not great.

**Our Solution: Base Image with Pre-installed Package**

We solve this by **pre-installing our ML package into the base Docker image**:

```dockerfile
# In pipe-fiction-codebase/Dockerfile
FROM python:3.12-slim
WORKDIR /app

# Install our package into the base image
COPY pyproject.toml README.md ./
COPY pipe_fiction/ ./pipe_fiction/
RUN uv pip install --system -e .
```

This allows us to **import** (not copy) our code in any component:

```python
@component(base_image="<your-registry>/<your-image-name>:<your-tag>")
def any_component():
    # Clean import - no code duplication!
    from pipe_fiction.data_generator import DataGenerator
    from pipe_fiction.data_processor import DataProcessor
    
    # Use the classes normally
    generator = DataGenerator()
    processor = DataProcessor()
```

### Debugging

Why is debugging a challenge?
- In the cluster, the code runs in pods that you can't easily debug into
- When executing components locally, you must pay attention to DAG order (without the local runner)
- The local runners are not readily supported by standard debugging workflows in IDEs like VS Code or PyCharm
- This often creates a long debug loop that includes waiting for CI/CD pipelines for image builds and pipeline execution

**Our Solution**: A combination of using the new local runner features of KFP and remote debugging sessions, as detailed below.

## Quick Start

### Prerequisites

- Python 3.12+
- Docker (for Docker runner)
- VS Code (recommended) or any debugpy-compatible IDE
- Access to a Kubeflow cluster (for remote execution)

### Setup

1. **Navigate to the demo:**
   ```bash
   # After cloning the example repository
   cd pipelines/pipe-fiction
   ```

2. **Install dependencies for the pipelines environment:**
   
   **Pipeline environment (KFP-specific packages):**
   ```bash
   cd pipelines
   uv sync
   source .venv/bin/activate  # Activate when working on pipeline code
   uv pip install -e ../pipe-fiction-codebase/  # Install custom package
   ```
   
3. **(RE-)Build the base Docker image if needed:**
   ```bash
   cd pipe-fiction-codebase
   export IMAGE_TAG=<your-registry>/<your-image-name>:<your-tag>
   docker build -t $IMAGE_TAG .
   ```
   More details on this in the `pipe-fiction-codebase` directory.

4. **Run the pipeline**
    
    ```bash
    cd pipelines
    ```

    Run locally using subprocesses (also works in KF-notebooks):
    ```bash
    python run_locally_in_subproc.py
    ```
    
    Run locally using Docker:
    ```bash
    python run_locally_in_docker.py
    ```
    
     Submit to the cluster from a Kubeflow notebook:
     ```bash
     python submit_to_cluster_from_kf_notebook.py
     ```

     Submit to the cluster from a remote machine (requires Keycloak setup — see [details below](#from-a-remote-machine--keycloak-auth)):
     ```bash
     python submit_to_cluster_from_remote.py
     ```

     **Don't have Keycloak or remote access set up?** You can still submit to the cluster:
     - **From a Kubeflow notebook:** clone this repo into a notebook, install deps, and run `python submit_to_cluster_from_kf_notebook.py` — no auth setup needed.
     - **Compile & upload manually:** `python -c "from kfp.compiler import Compiler; from pipeline import example_pipeline; Compiler().compile(example_pipeline, 'pipeline.yaml')"`, then upload `pipeline.yaml` through the KFP UI.

## Repository Organization

This demo is structured to demonstrate **separation** between standard Python code and KFP orchestration setup:

### Code Package (`pipe-fiction-codebase/`)

Contains the core logic as a **standalone Python package**. This Python package is not KFP-related and can be independently developed, tested, and debugged. The only thing that reminds us of K8s is the Dockerfile. The important thing is that it can be installed as a package.

```
pipe-fiction-codebase/
├── pipe_fiction/
│   ├── data_generator.py   # Generate sample data
│   └── data_processor.py   # Data transformation logic
├── Dockerfile              # Containerization with package installation
└── pyproject.toml          # Package definition
```

### Pipeline Orchestration (`pipelines/`)

Contains KFP-specific orchestration code:

```
pipelines/
├── components.py                          # KFP component definitions (import from base image)
├── pipeline.py                            # Pipeline assembly
├── run_locally_in_subproc.py              # Local execution using SubprocessRunner
├── run_locally_in_docker.py               # Local execution using DockerRunner
├── submit_to_cluster_from_kf_notebook.py  # Submission from a Kubeflow notebook
├── submit_to_cluster_from_remote.py       # Remote submission (Keycloak auth)
├── .venv/                                 # Virtual environment with custom package
└── utils/                                 # KFP utilities, auth, and patches
```

**Local Package Installation for IDE Support:**

The pipelines directory also contains a virtual environment where, alongside KFP-specific packages, the custom package is installed in development mode:

```bash
# Install the custom package locally for IDE support
uv pip install -e ../pipe-fiction-codebase/
```

This enables full IDE integration:
- Autocomplete and IntelliSense for imported package code
- Type checking and error detection in component definitions
- "Go to definition" works across package imports
- Refactoring support across the entire codebase

*Note: this trick only works when there are no dependency conflicts between the Python venvs in the pipelines folder and the custom packages. As soon as there are multiple packages with significantly different dependencies that should run in different KFP components, this trick no longer works.*

## Execution Environments

As indicated in the quick start section, there are (at least) three ways to execute the pipeline that uses logic from the custom package in tasks within the DAG:

### 1. Subprocess Runner (Fastest Development)

**Best for:** Quick iteration, algorithm development, initial testing

In this setup, the pipeline is run on your local machine using subprocesses.

```bash
cd pipelines
python run_locally_in_subproc.py
```

**Workflow**

A typical workflow using the subprocess runner could look like this:
1. Implement changes in component or custom package code
2. Run `python run_locally_in_subproc.py` to see if it works
3. Set breakpoints using the debugger or IDE to figure out what's wrong
4. Build and push Docker image when ready for submission to the cluster (this could also be done in a CI/CD pipeline):
   `docker build -t <your-registry>/<your-image-name>:<your-tag> . && docker push` 
5. Update image reference in pipeline components if needed
6. Submit pipeline to cluster: `python submit_to_cluster_from_kf_notebook.py` (from a KF notebook) or `python submit_to_cluster_from_remote.py` (from a remote machine)

Note that this workflow also works inside Kubeflow notebooks.

**Advantages:**
- Fastest execution - no container overhead
- Live code changes - no rebuilds needed
- Local Package Access - SubprocessRunner uses the package installed in the local .venv
- No Image Rebuilds - Code changes are immediately available without Docker builds

**Limitations:**
- Environment differences - may not match production environment exactly
- Dependency conflicts - uses local Python environment
- Limited isolation - no containerization benefits
- Lightweight components only - this does not work for container components
- Remote debugging required - CLI-based debuggers (like `pdb` with `breakpoint()`) work directly, but IDE debugging requires remote debugging setup

### 2. Docker Runner (Container-based Development)

**Best for:** Pipelines with container components and multiple differing environments in the KFP tasks

This setup is similar to the local execution in subprocesses, however in this case the local Docker engine on your machine is used to run the pipeline tasks inside Docker containers.

```bash
cd pipelines
python run_locally_in_docker.py
```

**Workflow**

For changes in the pipeline directory:
1. Modify files in `pipelines/` directory (components, pipeline definitions, pipeline arguments)
2. Run `python run_locally_in_docker.py` - changes are immediately reflected
3. Submit to cluster when ready

For changes in the custom Python package:
1. Modify code in `pipe-fiction-codebase/`
2. Rebuild Docker image locally (no push needed):
   `docker build -t <your-registry>/<your-image-name>:<your-tag> .` 
3. Run `python run_locally_in_docker.py` to test with new image
4. To debug the code inside the components, you'll need to use remote debugging (see dedicated section below)
5. Rebuild the image if needed and push it to your registry:
   `docker push <your-registry>/<your-image-name>:<your-tag>`
6. Update image reference in pipeline components if needed
7. Submit pipeline to cluster: `python submit_to_cluster_from_kf_notebook.py` or `python submit_to_cluster_from_remote.py`

**Advantages:**
- Production environment - identical to cluster execution
- Debugging support over remote debugger - step into containerized code
- Dependency isolation - no local conflicts

**Limitations:**
- Port forwarding needed - to connect debugger or any other tools 
- Slower iteration - container startup overhead
- Docker dependency - requires Docker runtime
- Image builds needed - for changes in the custom Python package
- Limited resource control - basic Docker constraints only, things like `task.set_env_vars()` or the caching mechanisms are not supported

### 3. Cluster Execution (In-Cluster Debugging)

**Best for:** In-cluster issues, cluster-specific debugging, resource-intensive workloads

Here we use the KFP backend as it runs inside the Kubernetes cluster, as intended.

**From a Kubeflow notebook** (no extra auth needed):
```bash
cd pipelines
python submit_to_cluster_from_kf_notebook.py
```

#### From a remote machine — Keycloak auth

Remote submission requires an OIDC client in Keycloak that supports the
Resource Owner Password Credentials (ROPC) grant. This is what lets the
script exchange a username + password for a token without a browser redirect.

#### Prerequisites: create the OIDC client (once)

A Keycloak admin creates the client once via the **Keycloak Admin Console**:

1. Log in to the Keycloak Admin Console (e.g. `https://<your-domain>/auth/admin/`)
2. Select the realm where your Kubeflow users are managed (e.g. `prokube`)
3. Go to **Clients** and click **Create client**
4. Configure it with these settings:
   - **Client ID:** `kfp-remote-user` (or any name you prefer)
   - **Client Protocol:** `openid-connect`
   - **Client authentication:** `On` (confidential client)
   - **Authorization:** `Off`
   - **Authentication flow** — enable **only**:
     - `Direct access grants` (this is the ROPC grant)
   - Disable everything else (`Standard flow`, `Implicit flow`, `Service accounts roles`, etc.)
5. Click **Save**, then go to the **Credentials** tab
6. Copy the **Client secret** — share this with users securely (e.g. via a secrets manager)

#### User: submit the pipeline

Once the admin has shared the client ID and secret, the user submits with:

```bash
cd pipelines
export KUBEFLOW_ENDPOINT=https://kubeflow.example.com
export KUBEFLOW_USERNAME=user@example.com
export KUBEFLOW_PASSWORD=your-password
export KEYCLOAK_URL=https://kubeflow.example.com
export KFP_CLIENT_SECRET=<secret-from-admin>
# Optional:
export KEYCLOAK_REALM=prokube          # default: "prokube"
export KFP_CLIENT_ID=kfp-remote-user   # default: "kfp-remote-user"
export KUBEFLOW_NAMESPACE=my-ns        # default: derived from username

python submit_to_cluster_from_remote.py
```

> **Note:** `KEYCLOAK_URL` should be the base URL where the Keycloak `/auth/`
> endpoint is reachable. In many setups this is the same as `KUBEFLOW_ENDPOINT`.

#### Without Keycloak or remote auth setup

If you don't have Keycloak set up or don't want to deal with remote
authentication, you can still submit pipelines to the cluster:

**Option A — Clone into a Kubeflow notebook and submit from there:**

From a Kubeflow notebook terminal (no extra auth needed — the notebook
session is already authenticated):

```bash
git clone <your-repo-url>
cd pipelines/pipe-fiction/pipelines
pip install -r requirements.txt   # or: uv sync && uv pip install -e ../pipe-fiction-codebase/
python submit_to_cluster_from_kf_notebook.py
```

**Option B — Compile the pipeline locally and upload via the KFP UI:**

```bash
cd pipelines
python -c "from kfp.compiler import Compiler; from pipeline import example_pipeline; Compiler().compile(example_pipeline, 'pipeline.yaml')"
```

Then open the Kubeflow Pipelines UI, go to **Pipelines > Upload pipeline**,
and upload the generated `pipeline.yaml` file.


**Cluster Execution Workflow**

For pipeline-only changes:
1. Modify files in `pipelines/` directory
2. Enable remote debugging for the task you want to debug (see remote debugging section for details)
3. Submit directly to cluster: `python submit_to_cluster_from_kf_notebook.py` or `python submit_to_cluster_from_remote.py`

For custom package changes:
1. Modify code in `pipe-fiction-codebase/`
2. Rebuild and push Docker image: `docker build -t <your-registry>/<your-image-name>:<your-tag> . && docker push`
3. Update image reference in pipeline components
4. Enable remote debugging for the task you want to debug (see remote debugging section for details)
5. Submit pipeline to cluster

**Advantages:**
- Real production environment - actual cluster resources
- All the KFP features - everything from caching to parallelism works here
- Scalability testing - real resource constraints
- Integration testing - with actual cluster services, without port forwards or similar

**Limitations:**
- Slowest feedback - submission and scheduling overhead
- Complex setup - requires cluster access and networking

## Remote Debugging

All execution environments (SubprocessRunner, DockerRunner, and cluster) support interactive debugging with [debugpy](https://github.com/microsoft/debugpy) for IDE integration. For CLI-based debugging, `breakpoint()` also works directly with the SubprocessRunner.

This section is organized as follows:
1. **Enabling Debugging in Components** - How to add debugging support to your KFP components (decorator or manual setup)
2. **Local Debugging Workflow** - How to debug pipelines running locally (SubprocessRunner or DockerRunner)
3. **Cluster Debugging with Port Forwarding** - How to debug pipelines running in a Kubernetes cluster
4. **IDE Setup** - VS Code configuration for connecting to the remote debugger

### 1. Enabling Debugging in Components

#### Debuggable Component Decorator (Recommended)

The easiest way to enable debugging is using our custom `@lightweight_debuggable_component` decorator that automatically injects debugging code:

```python
from utils.debuggable_component import lightweight_debuggable_component

@lightweight_debuggable_component(base_image="<your-registry>/<your-image-name>:<your-tag>")
def your_component_name(debug: bool = False):
    # Your component logic here - debugging code is auto-injected!
    from pipe_fiction.data_processor import DataProcessor
    processor = DataProcessor()
    return processor.process()
```

**Features:**
- Automatic debugging code injection (no boilerplate)
- Supports both `debugpy` (VS Code) and `remote-pdb` (CLI) debuggers
- Configurable debug ports
- Works with all KFP component parameters

**Usage examples:**
```python
# Default debugpy on port 5678
@lightweight_debuggable_component(base_image="my-image:latest")
def my_component(debug: bool = False): ...

# Remote pdb on custom port
@lightweight_debuggable_component(
    base_image="my-image:latest",
    debugger_type="remote-pdb",
    debug_port=4444
)
def my_component(debug: bool = False): ...
```

#### Manual Component Setup (Alternative)

For manual setup or when not using the decorator, components can be configured with debugging code directly:

```python
@component(base_image="<your-registry>/<your-image-name>:<your-tag>", packages_to_install=["debugpy"])
def your_component_name(debug: bool = False):
    if debug:
        import debugpy
        debugpy.listen(("0.0.0.0", 5678))
        debugpy.wait_for_client()
    
    # Your component logic here...
```

### 2. Local Debugging Workflow

1. **Enable debug mode** by passing `debug=True` to your component in the pipeline definition:
   ```python
   # In pipeline.py
   task = your_component_name(debug=True)
   ```

2. **Start the pipeline locally:**
   
   SubprocessRunner:
   ```bash
   python run_locally_in_subproc.py
   ```
   
   DockerRunner:
   ```bash
   python run_locally_in_docker.py
   ```

3. **Connect your debugger** - The pipeline will pause and wait for a debugger connection on port 5678. Use the appropriate VS Code configuration (see [IDE Setup](#4-ide-setup-vs-code)) to attach:
   - **SubprocessRunner**: Use "Pipeline: Remote SubprocessRunner" - no path mapping needed since the code runs directly on your machine.
   - **DockerRunner**: Use "Pipeline: Remote Debugging" - includes path mappings between your local `pipe-fiction-codebase/` and `/app` inside the container.

4. **Debug interactively** - Set breakpoints in your pipeline components or the imported package code, step through execution, and inspect variables.

### 3. Cluster Debugging with Port Forwarding

When debugging pipelines running in the cluster, an additional port-forwarding step is needed to connect your local IDE to the pod:

1. **Enable debug mode** and submit the pipeline to the cluster (see [Cluster Execution](#3-cluster-execution-in-cluster-debugging)).

2. **Set up port forwarding** to the pipeline pod:
   ```bash
   # Find your pipeline pod
   kubectl get pods | grep your-pipeline

   # Forward debug port
   kubectl port-forward pod/your-pod-name 5678:5678
   ```

3. **Connect your debugger** using the "Pipeline: Remote Debugging" VS Code configuration.

### 4. IDE Setup (VS Code)

Create `.vscode/launch.json` (this file is already included in the repo):

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Pipeline: Remote SubprocessRunner",
            "type": "debugpy",
            "request": "attach",
            "connect": {
                "host": "localhost",
                "port": 5678
            },
            "justMyCode": false,
            "subProcess": true
        },
        {
            "name": "Pipeline: Remote Debugging",
            "type": "debugpy",
            "request": "attach",
            "connect": {
                "host": "localhost",
                "port": 5678
            },
            "pathMappings": [
                {
                    "localRoot": "${workspaceFolder}/pipe-fiction-codebase",
                    "remoteRoot": "/app"
                }
            ],
            "justMyCode": false,
            "subProcess": true
        }
    ]
}
```

> **Note:** While these examples use VS Code with debugpy, any IDE that supports the [Debug Adapter Protocol](https://microsoft.github.io/debug-adapter-protocol/) (DAP) can connect to debugpy — including PyCharm, Neovim (with nvim-dap), and others.

## Technical Implementation Notes

### KFP Version Compatibility

This demo includes monkey patches for older KFP versions (pre-2.14) to enable:
- Port forwarding for debugging
- Environment variable injection
- Volume mounting for data access

in the DockerRunner of KFP local.

These patches provide forward compatibility and will be obsolete when upgrading to KFP 2.14+.

### Debugging Architecture

The debugging setup works by:
1. **Injecting debugpy** into pipeline components via the `debug` parameter
2. **Port forwarding** from container to host (for Docker/cluster execution)
3. **Path mapping** between local IDE and remote container (for Docker/cluster execution)
4. **Unified debugging experience** across all execution environments
