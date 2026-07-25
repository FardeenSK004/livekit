"""Cartesia TTS helpers — voice resolution + key list."""

from app.config import settings
from app.config.constants import DEFAULT_VOICE_ID, VOICE_MAP


def resolve_voice(voice_name: str | None) -> str:
    if not voice_name:
        return DEFAULT_VOICE_ID
    return VOICE_MAP.get(str(voice_name).lower(), str(voice_name))


def api_keys() -> list[str]:
    keys = settings.cartesia_api_keys_list
    if settings.CARTESIA_API_KEY and settings.CARTESIA_API_KEY not in keys:
        keys = [settings.CARTESIA_API_KEY, *keys]
    return keys
