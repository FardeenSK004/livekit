"""Template for creating a new LLM tool.
Copy this file, rename, and implement the function body."""

from __future__ import annotations


async def your_tool_name(param1: str, param2: int = 0) -> str:
    """Tool description — this is what the LLM sees.

    Args:
        param1: Description of param1
        param2: Description of param2 (default: 0)
    """
    return f"Processed {param1} with value {param2}"
