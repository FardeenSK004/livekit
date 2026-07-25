"""Voice pipeline assembly — STT → LLM → TTS → AgentSession."""

from __future__ import annotations

from typing import Any

from livekit.agents import AgentSession, TurnHandlingOptions, inference

from app.config import settings
from app.config.constants import DEFAULT_VOICE_ID, VOICE_MAP


def resolve_voice_id(voice_input: str | None) -> str:
    if not voice_input or voice_input in (None, "null", "None"):
        return DEFAULT_VOICE_ID
    return VOICE_MAP.get(str(voice_input).lower(), str(voice_input))


def resolve_model_name(metadata: dict[str, Any]) -> str:
    ai_payload = metadata.get("ai_payload") or {}
    if not isinstance(ai_payload, dict):
        ai_payload = {}
    model = ai_payload.get("ai_model") or metadata.get("model") or "openai"
    return str(model).lower()


def resolve_voice_config(metadata: dict[str, Any]) -> tuple[str, str, float]:
    """Return (voice_input, voice_id, voice_speed) from call metadata."""
    ai_payload = metadata.get("ai_payload") or {}
    if not isinstance(ai_payload, dict):
        ai_payload = {}

    _raw_voice = (
        ai_payload.get("voice_id")
        or metadata.get("voice_id")
        or metadata.get("voice_name")
        or metadata.get("voice")
        or "arushi"
    )
    voice_input = "arushi" if _raw_voice in (None, "null", "None") else _raw_voice
    voice_id = resolve_voice_id(str(voice_input))

    voice_speed = ai_payload.get("voice_speed") or metadata.get("voice_speed") or 1
    try:
        voice_speed = float(voice_speed)
        voice_speed = max(0.1, min(2.0, voice_speed))
    except (ValueError, TypeError):
        voice_speed = 1.0

    return str(voice_input), voice_id, voice_speed


def create_vad():
    from livekit.plugins import silero

    return silero.VAD.load(
        min_speech_duration=0.08,
        min_silence_duration=0.15,
    )


def create_stt():
    from livekit.plugins import deepgram

    kwargs: dict[str, Any] = {
        "model": "nova-3",
        "language": "hi",
        "smart_format": True,
        "numerals": True,
    }
    if settings.DEEPGRAM_API_KEY:
        kwargs["api_key"] = settings.DEEPGRAM_API_KEY
    return deepgram.STT(**kwargs)


def create_llm(metadata: dict[str, Any]):
    """Create LLM based on metadata ai_payload.ai_model field."""
    from livekit.plugins import google, openai

    model_name = resolve_model_name(metadata)

    if model_name == "gemini":
        return google.LLM(model="gemini-2.5-flash")
    if model_name == "deepseek":
        deepseek_key = settings.DEEPSEEK_API_KEY
        if not deepseek_key:
            return openai.LLM(model="gpt-4o-mini")
        return openai.LLM(
            model="deepseek-v4-flash",
            api_key=deepseek_key,
            base_url="https://api.deepseek.com",
        )
    return openai.LLM(model="gpt-4o-mini")


def create_tts(voice_id: str, voice_speed: float, language: str = "en"):
    """TTS via LiveKit Inference (cartesia/sonic-3)."""
    return inference.TTS(
        model="cartesia/sonic-3",
        voice=voice_id,
        language=str(language).lower() if language else "en",
        extra_kwargs={"speed": voice_speed},
    )


def create_turn_detector():
    from livekit.plugins.turn_detector.multilingual import MultilingualModel

    return MultilingualModel()


def create_agent_session(llm_engine, tts_engine) -> AgentSession:
    """Build a fully configured AgentSession matching production mantra settings."""
    return AgentSession(
        turn_handling=TurnHandlingOptions(
            turn_detection=create_turn_detector(),
            endpointing={
                "mode": "dynamic",
                "min_delay": 0.1,
                "max_delay": 0.35,
            },
            interruption={
                "mode": "vad",
                "resume_false_interruption": True,
                "false_interruption_timeout": 0.5,
                "min_words": 1,
            },
            preemptive_generation={
                "preemptive_tts": True,
            },
        ),
        vad=create_vad(),
        stt=create_stt(),
        llm=llm_engine,
        tts=tts_engine,
    )
