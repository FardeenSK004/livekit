"""LLM model registry helpers."""

from __future__ import annotations

SUPPORTED_MODELS = ("openai", "gemini", "deepseek")


def normalize_model_name(name: str | None) -> str:
    if not name:
        return "openai"
    lower = name.lower().strip()
    if lower in SUPPORTED_MODELS:
        return lower
    if "gemini" in lower:
        return "gemini"
    if "deepseek" in lower:
        return "deepseek"
    return "openai"
