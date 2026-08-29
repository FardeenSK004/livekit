"""Voice agent pipeline factory for LLM, STT, TTS, and VAD."""

import os
import httpx
import logging
from typing import Optional
from openai import AsyncClient as OpenAIAsyncClient
from livekit.agents import llm, inference
from livekit.plugins import openai, google, silero, deepgram

logger = logging.getLogger("core.agent.pipeline_factory")
POST_CALL_LLM_MODEL = os.getenv("POST_CALL_LLM_MODEL", "deepseek-v4-pro")
LIVE_LLM_MODEL = os.getenv("LIVE_LLM_MODEL", "deepseek-v4-flash")

VOICE_MAPPING = {
    "gemma": "62ae83ad-4f6a-430b-af41-a9bede9286ca",
    "alistair": "c8f7835e-28a3-4f0c-80d7-c1302ac62aae",
    "sunny": "156fb8d2-335b-4950-9cb3-a2d33befec77",
    "tyler": "820a3788-2b37-4d21-847a-b65d8a68c99a",
    "vikas": "adf97b9d-905c-41de-9fe9-afb387116d06",
    "camila": "bef2ba57-5c10-433b-b215-3bef35110a81",
    "renata": "d3793b7b-4996-409c-9d59-96dd09f47717",
    "arushi": "95d51f79-c397-46f9-b49a-23763d3eaa2d",
    "sia": "4459a9a5-69d6-4680-b970-e13dc51845b6",
    "sneha": "6b02ffe5-e3cb-48c0-a023-c72f85953375",
    "kavita": "56e35e2d-6eb6-4226-ab8b-9776515a7094",
    "katie": "f786b574-daa5-4673-aa0c-cbe3e8534c02",
    "cathy": "e8e5fffb-252c-436d-b842-8879b84445b6",
}


def resolve_voice_id(voice_input: Optional[str]) -> str:
    """Resolve a voice name or UUID to a valid Cartesia voice ID."""
    if not voice_input or voice_input in ("null", "None"):
        return VOICE_MAPPING["arushi"]
    return VOICE_MAPPING.get(str(voice_input).lower(), str(voice_input))


def build_post_call_llm() -> llm.LLM:
    """Build dedicated DeepSeek LLM engine for post-call structured analysis."""
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    if not deepseek_key:
        return google.LLM(model="gemini-2.5-flash")

    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=15.0, read=60.0, write=15.0, pool=15.0),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=5, keepalive_expiry=120),
    )
    client = OpenAIAsyncClient(
        api_key=deepseek_key,
        base_url="https://api.deepseek.com",
        http_client=http_client,
    )
    return openai.LLM(
        model=POST_CALL_LLM_MODEL,
        client=client,
        timeout=httpx.Timeout(connect=15.0, read=60.0, write=15.0, pool=15.0),
    )


def build_live_llm(model_preference: str = "deepseek") -> llm.LLM:
    """Build live conversational DeepSeek LLM for agent speech turns."""
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    if model_preference == "gemini":
        return google.LLM(model="gemini-2.5-flash")

    if deepseek_key:
        http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=15.0, read=60.0, write=15.0, pool=15.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=5, keepalive_expiry=120),
        )
        client = OpenAIAsyncClient(
            api_key=deepseek_key,
            base_url="https://api.deepseek.com",
            http_client=http_client,
        )
        return openai.LLM(
            model=LIVE_LLM_MODEL,
            client=client,
            timeout=httpx.Timeout(connect=15.0, read=60.0, write=15.0, pool=15.0),
        )

    return google.LLM(model="gemini-2.5-flash")


def build_stt(language: str = "en"):
    """Build Deepgram Nova-3 STT plugin."""
    return deepgram.STT(
        model="nova-3",
        language=language,
        smart_format=True,
        punctuate=True,
        numerals=True,
        endpointing_ms=25,
        no_delay=True,
    )


def build_tts(voice: str = "arushi", speed: float = 1.0, language: str = "en"):
    """Build Cartesia Sonic-3 TTS via LiveKit Inference."""
    voice_id = resolve_voice_id(voice)
    try:
        speed = float(speed)
        speed = max(0.1, min(2.0, speed))
    except (ValueError, TypeError):
        speed = 1.0

    return inference.TTS(
        model="cartesia/sonic-3",
        voice=voice_id,
        language=language,
        extra_kwargs={"speed": speed},
    )


def build_vad():
    """Build Silero VAD plugin."""
    return silero.VAD.load(
        min_speech_duration=0.10,
        min_silence_duration=0.25,
        prefix_padding_duration=0.20,
    )
