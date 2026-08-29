"""Voice presets and audio configurations."""

from constants.voices import DEFAULT_VOICE_ID, DEFAULT_VOICE_SPEED, VOICE_MAPPING


def resolve_voice_id(voice_name: str | None) -> str:
    """Resolve voice name to voice UUID."""
    if not voice_name:
        return DEFAULT_VOICE_ID
    cleaned = str(voice_name).strip().lower()
    return VOICE_MAPPING.get(cleaned, DEFAULT_VOICE_ID)
