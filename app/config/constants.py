"""Application constants — all magic strings in one place."""

from __future__ import annotations

# ── Voice Mapping (Cartesia Sonic voice IDs) ───────────────────────────
VOICE_MAP: dict[str, str] = {
    "gemma": "62ae83ad-4f6a-430b-af41-a9bede9286ca",
    "alistair": "c8f7835e-28a3-4f0c-80d7-c1302ac62aae",
    "sunny": "156fb8d2-335b-4950-9cb3-a2d33befec77",
    "tyler": "820a3788-2b37-4d21-847a-b65d8a68c99a",
    "vikas": "adf97b9d-905c-41de-9fe9-afb387116d06",
    "camila": "bef2ba57-5c10-433b-b215-3bef35110a81",
    "renata": "d3793b7b-4996-409c-9d59-96dd09f47717",
    "arushi": "95d51f79-c397-46f9-b49a-23763d3eaa2d",
}

# Alias matching legacy name in mantra/agent.py
VOICE_MAPPING = VOICE_MAP

DEFAULT_VOICE_ID = VOICE_MAP["arushi"]

# ── SIP / Handoff ──────────────────────────────────────────────────────
# Runtime transfer numbers come from settings.TRANSFER_NUMBERS (JSON env).
# These placeholders exist only as documentation defaults for local tests.
TRANSFER_NUMBERS: dict[str, str] = {}

TRANSFER_DEFAULT_NUMBER: str = ""

SIP_DEFAULT_ADDRESS_ZADARMA: str = "sip.zadarma.com"
SIP_DEFAULT_ADDRESS_TWILIO: str = "live-kit-mc.pstn.twilio.com"

# ── Call Limits ────────────────────────────────────────────────────────
CALL_DURATION_LIMIT_SECONDS: int = 180  # 3 min hard limit
INACTIVITY_TIMEOUT_SECONDS: int = 10  # no response → disconnect

# ── Farewell Detection (from agent.py safety net) ──────────────────────
FAREWELL_PHRASES: list[str] = [
    "goodbye",
    "good bye",
    "bye bye",
    "take care",
    "have a great day",
    "have a good day",
    "have a nice day",
    "thanks for calling",
    "thank you for calling",
    "talk to you later",
    "see you later",
]

# ── Capacity (defaults; prefer settings.* at runtime) ──────────────────
MAX_CONCURRENCY: int = 5
LIVEKIT_MAX_ROOMS: int = 20
AGENT_MAX_WORKERS: int = 20

# ── Auth ───────────────────────────────────────────────────────────────
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRY_HOURS: int = 24

# ── Redis keys ─────────────────────────────────────────────────────────
QUEUE_PENDING: str = "queue:pending"
CALLS_ACTIVE: str = "calls:active"
