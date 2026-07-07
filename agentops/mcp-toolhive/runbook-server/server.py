import os
import re
from pathlib import Path

from fastmcp import FastMCP


RUNBOOK_DIR = Path(os.environ.get("RUNBOOK_DIR", "/data/runbooks"))
RUNBOOK_DIR.mkdir(parents=True, exist_ok=True)

mcp = FastMCP("workspace-runbooks")


def _safe_name(name: str) -> str:
    slug = name.removesuffix(".md").strip().lower()
    slug = re.sub(r"[^a-z0-9._-]+", "-", slug).strip("-._")
    if not slug:
        raise ValueError("Runbook name must contain at least one letter or number")
    return f"{slug}.md"


def _runbook_path(name: str) -> Path:
    path = (RUNBOOK_DIR / _safe_name(name)).resolve()
    if RUNBOOK_DIR.resolve() not in path.parents:
        raise ValueError("Invalid runbook path")
    return path


@mcp.tool
def list_runbooks() -> list[str]:
    """List available runbook names."""
    return sorted(path.stem for path in RUNBOOK_DIR.glob("*.md"))


@mcp.tool
def get_runbook(name: str) -> str:
    """Return the Markdown content of a runbook."""
    path = _runbook_path(name)
    if not path.exists():
        raise ValueError(f"Runbook not found: {name}")
    return path.read_text(encoding="utf-8")


@mcp.tool
def save_runbook(name: str, content: str) -> str:
    """Create or replace a runbook with Markdown content."""
    path = _runbook_path(name)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return path.stem


@mcp.tool
def search_runbooks(query: str) -> list[dict[str, str]]:
    """Search runbook names and content with simple case-insensitive text matching."""
    needle = query.strip().lower()
    if not needle:
        raise ValueError("Query must not be empty")

    matches: list[dict[str, str]] = []
    for path in sorted(RUNBOOK_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        haystack = f"{path.stem}\n{content}".lower()
        if needle not in haystack:
            continue
        lines = [line.strip() for line in content.splitlines() if needle in line.lower()]
        matches.append({
            "name": path.stem,
            "snippet": lines[0] if lines else content[:160],
        })
    return matches


@mcp.tool
def delete_runbook(name: str) -> bool:
    """Delete a runbook. Returns true when a file was deleted."""
    path = _runbook_path(name)
    if not path.exists():
        return False
    path.unlink()
    return True


if __name__ == "__main__":
    mcp.run()
