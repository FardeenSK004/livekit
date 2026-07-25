"""Load prompt markdown files from the prompts/ directory."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


@lru_cache(maxsize=32)
def load_prompt(name: str) -> str:
    """Load a prompt by stem name, e.g. load_prompt('system') -> prompts/system.md."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()
