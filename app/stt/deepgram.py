"""Deepgram STT configuration helpers."""

from app.config import settings


def deepgram_defaults() -> dict:
    return {
        "model": "nova-3",
        "language": "hi",
        "api_key": settings.DEEPGRAM_API_KEY or None,
    }
