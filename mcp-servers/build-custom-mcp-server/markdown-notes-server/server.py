import os
import re
import shutil
from pathlib import Path

from fastmcp import FastMCP


NOTE_DIR = Path(os.environ.get("NOTE_DIR", "/data/notes"))
SEED_NOTE_DIR = Path(os.environ.get("SEED_NOTE_DIR", "/app/seed-notes"))

NOTE_DIR.mkdir(parents=True, exist_ok=True)

mcp = FastMCP("markdown-notes")


def _seed_notes() -> None:
    if any(NOTE_DIR.glob("*.md")) or not SEED_NOTE_DIR.exists():
        return
    for source in SEED_NOTE_DIR.glob("*.md"):
        shutil.copyfile(source, NOTE_DIR / source.name)


def _safe_name(name: str) -> str:
    slug = name.removesuffix(".md").strip().lower()
    slug = re.sub(r"[^a-z0-9._-]+", "-", slug).strip("-._")
    if not slug:
        raise ValueError("Runbook name must contain at least one letter or number")
    return f"{slug}.md"


def _note_path(name: str) -> Path:
    path = (NOTE_DIR / _safe_name(name)).resolve()
    if NOTE_DIR.resolve() not in path.parents:
        raise ValueError("Invalid note path")
    return path


@mcp.tool
def list_notes() -> list[str]:
    """List available note names."""
    return sorted(path.stem for path in NOTE_DIR.glob("*.md"))


@mcp.tool
def get_note(name: str) -> str:
    """Return the Markdown content of a note."""
    path = _note_path(name)
    if not path.exists():
        raise ValueError(f"Note not found: {name}")
    return path.read_text(encoding="utf-8")


@mcp.tool
def save_note(name: str, content: str) -> str:
    """Create or replace a note with Markdown content."""
    path = _note_path(name)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return path.stem


@mcp.tool
def search_notes(query: str) -> list[dict[str, str]]:
    """Search note names and content with simple case-insensitive text matching."""
    needle = query.strip().lower()
    if not needle:
        raise ValueError("Query must not be empty")

    matches: list[dict[str, str]] = []
    for path in sorted(NOTE_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        haystack = f"{path.stem}\n{content}".lower()
        if needle not in haystack:
            continue
        lines = [
            line.strip() for line in content.splitlines() if needle in line.lower()
        ]
        matches.append(
            {
                "name": path.stem,
                "snippet": lines[0] if lines else content[:160],
            }
        )
    return matches


@mcp.tool
def delete_note(name: str) -> bool:
    """Delete a note. Returns true when a file was deleted."""
    path = _note_path(name)
    if not path.exists():
        return False
    path.unlink()
    return True


if __name__ == "__main__":
    _seed_notes()
    mcp.run()
