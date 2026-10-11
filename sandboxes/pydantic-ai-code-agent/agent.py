"""Pydantic AI agent that uses a prokube Sandbox as its execution toolset."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from prokube.sandbox import Sandbox
from pydantic_ai import Agent, RunContext


DEFAULT_MODEL = "openai:gpt-4o-mini"
DEFAULT_POOL = "sandbox-sdk-quickstart"
IN_CLUSTER_AGENT_GATEWAY = "http://agentgateway-proxy.agentgateway-system.svc.cluster.local"
SERVICE_ACCOUNT_NAMESPACE = Path(
    "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
)


@dataclass
class SandboxDeps:
    """Dependencies available to Pydantic AI tools."""

    sandbox: Sandbox


def configure_managed_lab_defaults() -> None:
    """Set SDK defaults for managed Labs without overriding explicit values."""

    if SERVICE_ACCOUNT_NAMESPACE.exists():
        workspace = SERVICE_ACCOUNT_NAMESPACE.read_text().strip()
        os.environ.setdefault("PROKUBE_API_URL", IN_CLUSTER_AGENT_GATEWAY)
        os.environ.setdefault("PROKUBE_WORKSPACE", workspace)
        os.environ.setdefault("PROKUBE_USER_ID", workspace)


def build_agent() -> Agent[SandboxDeps, str]:
    """Create the Pydantic AI agent and register sandbox-backed tools."""

    agent = Agent(
        os.environ.get("PYDANTIC_AI_MODEL", DEFAULT_MODEL),
        deps_type=SandboxDeps,
        system_prompt=(
            "You are a coding agent. Use the sandbox tools to run Python, run "
            "shell commands, and read or write files under /workspace. Keep "
            "outputs concise. Do not print secrets or environment variables "
            "unless the user explicitly asks for a safe diagnostic."
        ),
    )

    @agent.tool
    def run_python(ctx: RunContext[SandboxDeps], code: str) -> str:
        """Run Python code in the stateful sandbox kernel."""

        result = ctx.deps.sandbox.run_code(code)
        return _format_result(result.stdout, result.stderr)

    @agent.tool
    def run_shell(ctx: RunContext[SandboxDeps], command: str) -> str:
        """Run a shell command inside the sandbox."""

        result = ctx.deps.sandbox.commands.run(command)
        output = _format_result(result.stdout, result.stderr)
        return f"exit_code={result.exit_code}\n{output}".strip()

    @agent.tool
    def write_file(ctx: RunContext[SandboxDeps], path: str, content: str) -> str:
        """Write a text file inside the sandbox."""

        _require_workspace_path(path)
        ctx.deps.sandbox.files.write(path, content)
        return f"Wrote {path}"

    @agent.tool
    def read_file(ctx: RunContext[SandboxDeps], path: str) -> str:
        """Read a text file from the sandbox."""

        _require_workspace_path(path)
        content = ctx.deps.sandbox.files.read(path)
        if isinstance(content, bytes):
            return content.decode("utf-8", errors="replace")
        return content

    @agent.tool
    def list_files(ctx: RunContext[SandboxDeps], path: str = "/workspace") -> str:
        """List files in a sandbox directory."""

        _require_workspace_path(path)
        files = ctx.deps.sandbox.files.list(path)
        return "\n".join(str(file_info) for file_info in files) or "No files found."

    return agent


def _format_result(stdout: str | None, stderr: str | None) -> str:
    parts = []
    if stdout:
        parts.append(f"stdout:\n{stdout}")
    if stderr:
        parts.append(f"stderr:\n{stderr}")
    return "\n\n".join(parts) or "No output."


def _require_workspace_path(path: str) -> None:
    if not path.startswith("/workspace/") and path != "/workspace":
        raise ValueError("This example only allows file access under /workspace")


def main() -> None:
    configure_managed_lab_defaults()

    pool = os.environ.get("SANDBOX_POOL", DEFAULT_POOL)
    task = " ".join(sys.argv[1:]) or (
        "Create /workspace/scores.csv with five rows of sample data, analyze it "
        "with Python, and write /workspace/report.md with the findings."
    )
    agent = build_agent()

    with Sandbox.from_pool(pool) as sandbox:
        result = agent.run_sync(task, deps=SandboxDeps(sandbox=sandbox))
        print(result.output)


if __name__ == "__main__":
    main()
