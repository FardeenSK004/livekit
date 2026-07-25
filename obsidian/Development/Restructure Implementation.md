# Restructure Implementation Guide

> **Parent Plan:** [[Architecture/Restructure Plan.md]]  
> **Status:** ✅ Complete + verified (**GO WITH CAVEATS**) — branch `feature/restructure`  
> **Last Updated:** 2026-07-25  
> **Total Duration:** ~25 days  
> **Strategy:** Parallel-safe phases — `mantra/` retained until Phase 8, then deleted.  
> **Verification:** [[Development/Restructure Verification Report.md|Restructure Verification Report]] · repo-root `report.md`

---

## Progress (2026-07-25)

| Phase | Status | Notes |
|-------|--------|-------|
| 0 Preparation | ✅ Done | Env/model/prompt audits against live `mantra/` |
| 1 Scaffold + Config | ✅ Done | `app/config/`, `prompts/`, `migrations/*.sql`, `config/` |
| 2 Models | ✅ Done | `app/models/*` Pydantic schemas |
| 3 Services | ✅ Done | livekit/redis/db/auth/webhook/s3/sip (+ providers/inbound/org) |
| 4 Routers + main | ✅ Done | Full SIP/webhook/dashboard/KB/org parity; 55 routes |
| 5 Agent subsystem | ✅ Done | Full entrypoint + tools/safety/finalize; `agent_name=mantra-agent` |
| 6 Dispatcher + routines | ✅ Done | Agent dispatch + SIP + zombie cleanup; `python -m app.routines` |
| 7 KB engine | ✅ Done | engine/chunker/retriever/ingestion; no mantra deps |
| 8 Tests + cleanup | ✅ Done | pytest green; entrypoints switched; `mantra/` deleted |
| Final verification | ✅ Done (caveats) | 7/7 unit; 39/39 endpoint smoke; JWT + invalid-JSON fixes; see report |

**Production entrypoints:** `mantra-agent` / `mantra-ui` / `app-agent` / `app-ui` / `app-dispatcher` → `app.*`

**Verification summary:** Safe to commit/push for review. Not production-ready until complete env (Postgres/JWT/SIP), MCP fix, and staged call smoke. Details: [[Development/Restructure Verification Report.md]].

---

## Execution Strategy

The old `mantra/` package and the new `app/` package coexist during migration. At each phase, you:

1. **Create** the new file in `app/`
2. **Import and test** it alongside the old code
3. **Switch** the old entrypoints to use the new package
4. **Delete** the old file only in Phase 8

This means the codebase is never in a broken state — you can deploy at any phase boundary.

---

## Phase 0: Preparation (Day 0)

### 0.1 — Read the entire codebase

Before writing a single line of new code, read every file in `mantra/` to understand what it does:

```bash
# Read all source files in full
wc -l mantra/*.py mcp/server.py

# Key files to understand (in order)
mantra/ui_server.py    # 2,863 lines — HTTP, SIP, dashboard, KB APIs
mantra/agent.py        # 1,617 lines — voice agent, tools, post-call
mantra/utils.py        # 534 lines — S3, DB, recording, analysis, webhook
mantra/knowledge_base.py  # 492 lines — KB engine + chunker
mantra/dispatcher.py   # 203 lines — queue consumer
mantra/email_alerts.py # 244 lines — SMTP alerts
mantra/retriever.py    # 50 lines — KB retriever cache
```

### 0.2 — Audit current `os.getenv()` calls

Find every env var reference so `config/settings.py` doesn't miss any:

```bash
grep -rn "os.getenv\|os.environ" mantra/ --include="*.py" | grep -v __pycache__ | sort
```

Save this list — it's the checklist for `config/settings.py`.

### 0.3 — Audit current Pydantic models

Check if any models already exist that can be reused:

```bash
grep -rn "BaseModel\|@dataclass" mantra/ --include="*.py" | grep -v __pycache__
```

### 0.4 — Audit current prompts

Find every hardcoded prompt string that needs to move to `prompts/`:

```bash
grep -rn "prompt\|instructions\|system_msg\|farewell\|FAREWELL" mantra/agent.py | head -40
```

---

## Phase 1: Scaffold + Config (Days 1-2)

### Step 1.1 — Create directory structure

Run these commands to create the full scaffold:

```bash
# Create the app package
mkdir -p app/config
mkdir -p app/models
mkdir -p app/routers
mkdir -p app/services
mkdir -p app/agent/tools
mkdir -p app/stt
mkdir -p app/llm
mkdir -p app/tts
mkdir -p app/kb
mkdir -p app/recording
mkdir -p app/dispatcher
mkdir -p app/routines
mkdir -p app/alerter

# Create prompts directory
mkdir -p prompts

# Create migrations directory
mkdir -p migrations

# Create tests directory structure
mkdir -p tests/test_services
mkdir -p tests/test_agent
mkdir -p tests/test_routers
mkdir -p tests/test_kb

# Create static in new location (move later, symlink for now)
mkdir -p app/static
```

### Step 1.2 — Create `__init__.py` files

Every sub-package needs an `__init__.py`. Create these minimal files:

**`app/__init__.py`**
```python
"""Mantra Voice Agent — restructured application package."""

__version__ = "0.1.0"
```

**`app/config/__init__.py`**
```python
from .settings import settings
from .constants import (
    VOICE_MAP,
    TRANSFER_NUMBERS,
    TRANSFER_DEFAULT_NUMBER,
    FAREWELL_PHRASES,
    CALL_DURATION_LIMIT_SECONDS,
    INACTIVITY_TIMEOUT_SECONDS,
    MAX_CONCURRENCY,
    LIVEKIT_MAX_ROOMS,
    AGENT_MAX_WORKERS,
)

__all__ = [
    "settings",
    "VOICE_MAP",
    "TRANSFER_NUMBERS",
    "TRANSFER_DEFAULT_NUMBER",
    "FAREWELL_PHRASES",
    "CALL_DURATION_LIMIT_SECONDS",
    "INACTIVITY_TIMEOUT_SECONDS",
    "MAX_CONCURRENCY",
    "LIVEKIT_MAX_ROOMS",
    "AGENT_MAX_WORKERS",
]
```

All other `__init__.py` files can be empty for now.

### Step 1.3 — Create `config/settings.py`

This is the most important file in the restructure. It replaces every `os.getenv()` call with a typed, validated setting.

**Source material to extract from:**
- `ui_server.py` lines 34-61 (env loading, JWT config)
- `ui_server.py` lines 75-120 (LiveKit clients)
- `agent.py` lines 1-50 (env vars, OpenTelemetry suppression)
- `dispatcher.py` lines 19-26 (capacity limits)
- `utils.py` lines 1-30 (DB, S3 config)
- `email_alerts.py` lines 22-28 (SMTP config)
- `.env.local` and `.env` files

```python
"""Application settings — single source of truth for all env vars.

Usage:
    from app.config import settings
    settings.LIVEKIT_URL  # str, validated at import time
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── LiveKit ────────────────────────────────────────────────────────
    LIVEKIT_URL: str = "ws://localhost:7880"
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""

    PLIVO_PROXY_URL: str = ""
    PLIVO_PROXY_API_KEY: str = ""
    PLIVO_PROXY_API_SECRET: str = ""

    # ── SIP Trunks ─────────────────────────────────────────────────────
    SIP_TRUNK_ID: str = ""
    SIP_TRUNK_ID_ZADARMA: str = ""
    SIP_TRUNK_ID_TWILIO: str = ""

    # ── Redis ──────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379"

    # ── PostgreSQL ─────────────────────────────────────────────────────
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "livekit"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: str = "5432"

    # ── JWT Auth ───────────────────────────────────────────────────────
    JWT_SECRET: str = ""
    ADMIN_USERNAME_HASH: str = ""
    ADMIN_PASSWORD_HASH: str = ""

    # ── Cartesia TTS ───────────────────────────────────────────────────
    CARTESIA_API_KEY: str = ""
    CARTESIA_API_KEYS: str = ""  # comma-separated, for FallbackAdapter

    # ── Deepgram STT ───────────────────────────────────────────────────
    DEEPGRAM_API_KEY: str = ""

    # ── OpenAI / LLM ───────────────────────────────────────────────────
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""

    # ── AWS S3 ─────────────────────────────────────────────────────────
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    AWS_S3_BUCKET_NAME: str = ""

    # ── MantraAssist Backend ───────────────────────────────────────────
    MANTRAASSIST_BACKEND_URL: str = ""
    MANTRAASSIST_WEBHOOK_SECRET: str = ""

    # ── SMTP Alerts ────────────────────────────────────────────────────
    SMTP_HOST: str = ""
    SMTP_PORT: str = "587"
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    ALERT_EMAIL_IDS: str = ""
    ADMIN_MAIL_ID: str = ""

    # ── Capacity ───────────────────────────────────────────────────────
    MAX_CONCURRENCY: int = 5
    LIVEKIT_MAX_ROOMS: int = 20
    AGENT_MAX_WORKERS: int = 20

    # ── Agent Behavior ─────────────────────────────────────────────────
    CALL_DURATION_LIMIT_SECONDS: int = 180
    INACTIVITY_TIMEOUT_SECONDS: int = 10
    LOCAL_INBOUND_MAPPINGS: bool = False

    # ── Feature Flags ──────────────────────────────────────────────────
    LIVEKIT_AGENTS_INFERENCE: bool = False
    OTEL_METRICS_EXPORTER: str = "none"
    OTEL_LOGS_EXPORTER: str = "none"
    OTEL_TRACES_EXPORTER: str = "none"

    model_config = {
        "env_file": ".env.local",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
    }


settings = Settings()

# ── Derived / computed values ─────────────────────────────────────────
CARTESIA_API_KEYS_LIST = [k.strip() for k in settings.CARTESIA_API_KEYS.split(",") if k.strip()]
```

**Verification:** Run this to ensure all env vars load correctly:

```python
python -c "from app.config.settings import settings; print(settings.LIVEKIT_URL)"
```

### Step 1.4 — Create `config/constants.py`

Extract all hardcoded magic strings, maps, and limits from the old files.

**Source material:**
- `agent.py` lines ~200-250 (VOICE_MAP)
- `agent.py` lines ~279-290 (TRANSFER_NUMBERS)
- `agent.py` lines ~700-750 (FAREWELL_PHRASES, limits)
- `ui_server.py` lines ~500-550 (SIP defaults)

```python
"""Application constants — all magic strings in one place."""


# ── Voice Mapping ──────────────────────────────────────────────────────
VOICE_MAP: dict[str, str] = {
    "arushi":   "95d51f79-c397-46f9-b49a-23763d3eaa2d",
    "gemma":    "62ae83ad-4f6a-430b-af41-a9bede9286ca",
    "alistair": "c8f7835e-28a3-4f0c-80d7-c1302ac62aae",
    "sunny":    "156fb8d2-335b-4950-9cb3-a2d33befec77",
    "tyler":    "820a3788-2b37-4d21-847a-b65d8a68c99a",
    "vikas":    "adf97b9d-905c-41de-9fe9-afb387116d06",
    "camila":   "bef2ba57-5c10-433b-b215-3bef35110a81",
    "renata":   "d3793b7b-4996-409c-9d59-96dd09f47717",
}

DEFAULT_VOICE_ID = VOICE_MAP["arushi"]

# ── SIP / Handoff ──────────────────────────────────────────────────────
TRANSFER_NUMBERS: dict[str, str] = {
    "refund":  "+919999999991",
    "support": "+919999999992",
    "billing": "+919999999993",
}

TRANSFER_DEFAULT_NUMBER: str = "+919999999990"

SIP_DEFAULT_ADDRESS_ZADARMA: str = "zadarma.example.com"
SIP_DEFAULT_ADDRESS_TWILIO: str = "live-kit-mc.pstn.twilio.com"

# ── Call Limits ────────────────────────────────────────────────────────
CALL_DURATION_LIMIT_SECONDS: int = 180  # 3 min hard limit
INACTIVITY_TIMEOUT_SECONDS: int = 10  # no response → disconnect

# ── Farewell Detection ─────────────────────────────────────────────────
FAREWELL_PHRASES: list[str] = [
    "goodbye", "bye", "thank you", "thanks", "that's all",
    "that is all", "i'm done", "im done", "see you",
]

# ── Capacity ───────────────────────────────────────────────────────────
MAX_CONCURRENCY: int = 5
LIVEKIT_MAX_ROOMS: int = 20
AGENT_MAX_WORKERS: int = 20

# ── Misc ───────────────────────────────────────────────────────────────
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRY_HOURS: int = 24
```

**Verification:** 
```python
python -c "from app.config.constants import VOICE_MAP; print(len(VOICE_MAP))"
```

### Step 1.5 — Create `config/logging.py`

Extract the `ColorFormatter` and logging setup from `agent.py` and `ui_server.py`.

**Source material:** `agent.py` lines 25-50, `ui_server.py` lines 37-42

```python
"""Logging configuration — ColorFormatter and setup helpers."""

import logging
import os
import sys

from colorama import Back, Fore, Style, init as colorama_init

colorama_init(autoreset=True)


class ColorFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG: Fore.CYAN,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.RED + Back.WHITE,
    }

    def format(self, record):
        record.raw_msg = record.getMessage()
        color = self.LEVEL_COLORS.get(record.levelno, Fore.WHITE)
        record.msg = f"{color}{record.msg}{Style.RESET_ALL}"
        return super().format(record)


def setup_logger(
    name: str,
    level: int = logging.INFO,
    fmt: str = "%(asctime)s INFO %(name)s: %(message)s",
) -> logging.Logger:
    """Create a configured logger for a module."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    _is_inference = os.getenv("LIVEKIT_AGENTS_INFERENCE") == "1"
    _proc_type = "Inference Subprocess" if _is_inference else "Main Worker"
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(
        ColorFormatter(
            f"%(asctime)s INFO (Type: {_proc_type}, PID: {os.getpid()}) {name}: %(message)s"
        )
    )
    logger.addHandler(_handler)
    logger.propagate = False
    return logger
```

### Step 1.6 — Extract prompts to `prompts/`

Read `agent.py` and find every hardcoded prompt string. Extract each to a `.md` file.

**Source lines to check:**
```
grep -n '"""\|prompt\|instructions\|system_msg\|SYSTEM\|You are' mantra/agent.py
```

Create each file in `prompts/`:

**`prompts/system.md`**
```markdown
You are a professional voice assistant from MantraCare. You are having a
conversation with a user over the phone.

Key rules:
1. Keep responses concise and conversational — this is a voice call.
2. Ask one question at a time.
3. Never break character.
4. Use the search_knowledge_base tool when you need factual information.
5. Use the transfer_to_human tool when the user asks for a human or you
   cannot resolve their issue.
6. Use the end_call tool only when the conversation is naturally complete.
```

**`prompts/handoff.md`**
```markdown
When the user requests a human, use transfer_to_human immediately.
Do NOT try to resolve the issue yourself once handoff is requested.
After calling transfer_to_human, respond with a brief confirmation
like "I'm connecting you to a specialist" and then remain silent.
```

**`prompts/farewell.md`**
```markdown
Detect when the user is saying goodbye. Farewell phrases include:
goodbye, bye, thank you, thanks, that's all, that is all, i'm done,
im done, see you. If detected, use end_call to gracefully disconnect.
```

**`prompts/analysis.md`**
```markdown
You are a call analysis system. Given a transcript, generate:
1. A one-paragraph summary of the call
2. The stage transition based on stageDetails
3. An appointment object (date_time, doctor, location) if present
4. A sentiment score from 1.0 to 10.0
```

**`prompts/guardrails.md`**
```markdown
## 5-Rule Absolute Override Framework

1. MANDATORY FACTUAL ANSWERS: Always answer factual questions directly
   before steering the conversation.
2. PRIMARY SOURCE CONSTRAINT: Use only KB content for specific facts
   (services, treatments, pricing, policies).
3. FACTUAL EXPLANATION VS PERSONALIZED ADVICE: You may explain conditions
   based on KB text, but never diagnose the user.
4. GENERAL KNOWLEDGE FALLBACK: You may answer general questions neutrally
   if not in the KB.
5. NO SOURCE-CITING LANGUAGE: Never say "according to my knowledge base"
   — just answer naturally.
```

---

## Phase 2: Models Layer (Days 3-4)

### Step 2.1 — Create Pydantic models

Examine every function signature in the old code that takes or returns a raw dict. Create typed models for each.

**Source material to analyze:**
- `ui_server.py` — webhook payloads, SIP trunk configs, dashboard responses, login requests
- `agent.py` — call metadata payload, agent state, tool results
- `utils.py` — call log records, analysis results
- `knowledge_base.py` — KnowledgePage dataclass (already exists)

**`app/models/call.py`**
```python
"""Call-related models."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class CallMetadata(BaseModel):
    prompt: str = ""
    client_name: str = ""
    call_id: str = ""
    lead_id: str = ""
    ai_payload: dict[str, Any] = Field(default_factory=dict)
    stage_id: int = 0
    stageDetails: list[dict[str, Any]] = Field(default_factory=list)
    client_custom_fields: dict[str, Any] = Field(default_factory=dict)
    client_phone: str = ""
    direction: str = "outbound"
    trunk_id: str = ""
    kb_id: str = ""
    kb_ids: list[str] = Field(default_factory=list)
    kb_tags: list[str] = Field(default_factory=list)
    org_id: str = ""
    process_id: str = ""
    transfer_numbers: dict[str, str] = Field(default_factory=dict)


class CallStatus(BaseModel):
    call_id: str
    status: str  # queued, ringing, active, completed, failed
    direction: str = "outbound"
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    sip_error: Optional[str] = None


class DispatchPayload(BaseModel):
    call_id: str
    phone_number: str
    trunk_id: str = ""
    metadata: CallMetadata = Field(default_factory=CallMetadata)
    room_name: str = ""
    sip_number: str = ""


class WebhookPayload(BaseModel):
    call_id: str
    direction: str
    phone_number: str
    metadata: CallMetadata

    model_config = {"extra": "ignore"}
```

**`app/models/agent.py`**
```python
"""Agent state and session models."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class AgentState(BaseModel):
    call_id: str = ""
    room_name: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    handoff_triggered: bool = False
    call_ended: bool = False
    inactivity_task: Optional[Any] = None
    farewell_task: Optional[Any] = None
    call_limiter_task: Optional[Any] = None
    kb_ids: list[str] = Field(default_factory=list)
    kb_tags: list[str] = Field(default_factory=list)


class ToolResult(BaseModel):
    success: bool
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class SessionData(BaseModel):
    room_name: str
    participant_identity: str
    agent_identity: str
    user_joined: bool = False
    user_spoke: bool = False
    started_at: Optional[float] = None
```

**`app/models/sip.py`**
```python
"""SIP trunk and telephony models."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SipProvider(str, Enum):
    TWILIO = "twilio"
    PLIVO = "plivo"
    ZADARMA = "zadarma"


class SipTrunkConfig(BaseModel):
    provider: SipProvider
    trunk_id: str = ""
    address: str = ""
    destination_country: str = "in"
    phone_number: str = ""


class SipParticipant(BaseModel):
    sip_trunk_id: str
    sip_number: str
    room_name: str
    participant_identity: str = ""


class SipError(str, Enum):
    NO_ANSWER = "No Answer"
    BUSY = "Busy"
    INCOMPLETE = "Incomplete"


SIP_ERROR_MAP: dict[str, SipError] = {
    "408": SipError.NO_ANSWER,
    "timeout": SipError.NO_ANSWER,
    "486": SipError.BUSY,
    "busy": SipError.BUSY,
    "decline": SipError.BUSY,
}
```

**`app/models/kb.py`**
```python
"""Knowledge base models."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class KnowledgePage(BaseModel):
    id: str
    kb_id: str
    title: str
    content: str
    source_type: str
    page_meta: dict[str, Any] = Field(default_factory=dict)
    content_in_text: str = ""
    created_at: Optional[datetime] = None
    similarity: float = 0.0


class IngestRequest(BaseModel):
    kb_id: str
    title: str = ""
    content: str = ""
    url: str = ""
    source_type: str = "text"
    document_id: str = ""
    tags: list[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    query: str
    kb_ids: list[str]
    top_k: int = 3
    tags: Optional[list[str]] = None


class SearchResult(BaseModel):
    results: list[KnowledgePage] = Field(default_factory=list)
    total: int = 0
```

**`app/models/dashboard.py`**
```python
"""Dashboard and metrics models."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class MetricsResponse(BaseModel):
    today_total_calls: int = 0
    answer_rate: float = 0.0
    avg_duration_seconds: float = 0.0


class ActiveCall(BaseModel):
    call_id: str
    room_name: str
    status: str
    started_at: Optional[str] = None
    duration_seconds: int = 0


class StreamEvent(BaseModel):
    pending_calls: int = 0
    active_calls: int = 0
    max_concurrency: int = 0
    active_call_details: list[ActiveCall] = Field(default_factory=list)
    timestamp: str = ""


class CallHistoryEntry(BaseModel):
    call_id: str
    status: str
    caller: str = ""
    duration_seconds: int = 0
    timestamp: str = ""
    recording_url: str = ""


class PaginatedResponse(BaseModel):
    items: list[Any] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
```

**`app/models/auth.py`**
```python
"""Authentication models."""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    token: str
    expires_in: int = 86400  # 24h


class TokenPayload(BaseModel):
    sub: str = ""
    exp: float = 0.0
    iat: float = 0.0
```

### Step 2.2 — Verification

```python
python -c "
from app.models.call import CallMetadata, DispatchPayload
from app.models.sip import SipProvider, SipTrunkConfig
from app.models.kb import IngestRequest, SearchRequest
print('All models load successfully')
"
```

---

## Phase 3: Services Layer (Days 5-8)

### Step 3.1 — Create `services/livekit.py`

Extract LiveKit API client management from `ui_server.py` lines 44-120.

**Source code location:** `ui_server.py` lines 44-50 (global client vars), lines 75-120 (lifespan creation), lines 200-280 (SIP participant creation, room management)

```python
"""LiveKit API client management.

Usage:
    from app.services.livekit import get_lk_client, create_room
    client = await get_lk_client()
"""

from livekit import api
from app.config import settings


class LiveKitService:
    """Manages LiveKit API clients (direct + Plivo proxy)."""

    def __init__(self):
        self._lk_client: api.LiveKitAPI | None = None
        self._plivo_client: api.LiveKitAPI | None = None

    async def start(self):
        api_key = settings.LIVEKIT_API_KEY
        api_secret = settings.LIVEKIT_API_SECRET
        lk_url = self._normalize_url(settings.LIVEKIT_URL)

        self._lk_client = api.LiveKitAPI(
            url=lk_url, api_key=api_key, api_secret=api_secret
        )

        if settings.PLIVO_PROXY_URL:
            plivo_url = self._normalize_url(settings.PLIVO_PROXY_URL)
            self._plivo_client = api.LiveKitAPI(
                url=plivo_url,
                api_key=settings.PLIVO_PROXY_API_KEY or api_key,
                api_secret=settings.PLIVO_PROXY_API_SECRET or api_secret,
            )

    async def stop(self):
        if self._lk_client:
            await self._lk_client.aclose()
        if self._plivo_client:
            await self._plivo_client.aclose()

    @property
    def lk(self) -> api.LiveKitAPI:
        if not self._lk_client:
            raise RuntimeError("LiveKit client not initialized. Call start() first.")
        return self._lk_client

    @property
    def plivo(self) -> api.LiveKitAPI:
        if not self._plivo_client:
            return self.lk  # fallback to direct
        return self._plivo_client

    async def create_room(self, room_name: str) -> None:
        await self.lk.room.create_room(api.CreateRoomRequest(name=room_name))

    async def delete_room(self, room_name: str) -> None:
        await self.lk.room.delete_room(api.DeleteRoomRequest(room=room_name))

    async def list_rooms(self) -> list[api.Room]:
        resp = await self.lk.room.list_rooms(api.ListRoomsRequest())
        return resp.rooms

    async def create_sip_participant(
        self,
        room_name: str,
        sip_trunk_id: str,
        sip_number: str,
        play_dialtone: bool = True,
    ) -> api.SIPParticipantInfo:
        from livekit.protocol import sip as proto_sip

        req = proto_sip.CreateSIPParticipantRequest(
            room_name=room_name,
            sip_trunk_id=sip_trunk_id,
            sip_call_to=sip_number,
            play_dialtone=play_dialtone,
        )
        return await self.lk.sip.create_sip_participant(req)

    def get_client_for_provider(self, provider: str) -> api.LiveKitAPI:
        if provider == "plivo":
            return self.plivo
        return self.lk

    @staticmethod
    def _normalize_url(url: str) -> str:
        if url.startswith("wss://"):
            return url.replace("wss://", "https://")
        if url.startswith("ws://"):
            return url.replace("ws://", "http://")
        return url


# Singleton
livekit_service = LiveKitService()
```

### Step 3.2 — Create `services/redis.py`

Extract from `ui_server.py` (scattered Redis calls) and `dispatcher.py`.

```python
"""Redis service — queue, active calls, capacity tracking."""

import json
import time
from typing import Any, Optional

import redis.asyncio as redis

from app.config import settings

QUEUE_PENDING = "queue:pending"
CALLS_ACTIVE = "calls:active"


class RedisService:
    def __init__(self):
        self._client: redis.Redis | None = None

    async def start(self):
        self._client = await redis.from_url(settings.REDIS_URL, decode_responses=True)

    async def stop(self):
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> redis.Redis:
        if not self._client:
            raise RuntimeError("Redis not initialized. Call start() first.")
        return self._client

    # ── Queue ──────────────────────────────────────────────────────────
    async def push_pending(self, payload: dict, score: float = 0):
        await self.client.zadd(QUEUE_PENDING, {json.dumps(payload): score})

    async def pop_pending(self) -> Optional[dict]:
        results = await self.client.zpopmin(QUEUE_PENDING)
        if not results:
            return None
        item, score = results[0]
        return json.loads(item)

    async def requeue(self, payload: dict, additional_score: float = 10):
        # Re-queue with higher score (lower priority)
        await self.push_pending(payload, time.time() + additional_score)

    async def pending_count(self) -> int:
        return await self.client.zcard(QUEUE_PENDING)

    # ── Active Calls ───────────────────────────────────────────────────
    async def add_active(self, call_id: str, room_name: str, metadata: dict):
        data = {"call_id": call_id, "room_name": room_name, "started_at": time.time(), **metadata}
        await self.client.hset(CALLS_ACTIVE, call_id, json.dumps(data))

    async def remove_active(self, call_id: str):
        await self.client.hdel(CALLS_ACTIVE, call_id)

    async def get_active(self, call_id: str) -> Optional[dict]:
        data = await self.client.hget(CALLS_ACTIVE, call_id)
        return json.loads(data) if data else None

    async def all_active(self) -> list[dict]:
        data = await self.client.hgetall(CALLS_ACTIVE)
        return [json.loads(v) for v in data.values()]

    async def active_count(self) -> int:
        return await self.client.hlen(CALLS_ACTIVE)

    # ── SIP Error Status ───────────────────────────────────────────────
    async def set_sip_error(self, call_id: str, error: str, ttl: int = 300):
        key = f"sip_error_status:{call_id}"
        await self.client.setex(key, ttl, error)

    async def get_sip_error(self, call_id: str) -> Optional[str]:
        key = f"sip_error_status:{call_id}"
        return await self.client.get(key)


redis_service = RedisService()
```

### Step 3.3 — Create `services/db.py`

Extract DB connection and CRUD from `ui_server.py` `get_db_connection()` and `utils.py` `save_call_log_to_db()`.

```python
"""PostgreSQL database service."""

import asyncpg
from app.config import settings


class DatabaseService:
    def __init__(self):
        self._pool: asyncpg.Pool | None = None

    async def start(self):
        self._pool = await asyncpg.create_pool(
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            database=settings.POSTGRES_DB,
            host=settings.POSTGRES_HOST,
            port=int(settings.POSTGRES_PORT),
            min_size=2,
            max_size=10,
        )

    async def stop(self):
        if self._pool:
            await self._pool.close()

    @property
    def pool(self) -> asyncpg.Pool:
        if not self._pool:
            raise RuntimeError("DB not initialized. Call start() first.")
        return self._pool

    async def save_call_log(self, call_id: str, call_log: str, status: str, recording_url: str):
        query = """
        INSERT INTO call_logs (call_id, call_log, status, recording_url)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (call_id) DO UPDATE
        SET call_log = EXCLUDED.call_log,
            status = EXCLUDED.status,
            recording_url = EXCLUDED.recording_url;
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, call_id, call_log, status, recording_url)

    async def get_call_logs(
        self, limit: int = 50, offset: int = 0
    ) -> list[dict]:
        query = """
        SELECT call_id, status, recording_url, created_at
        FROM call_logs
        ORDER BY created_at DESC
        LIMIT $1 OFFSET $2
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, limit, offset)
            return [dict(r) for r in rows]

    async def get_today_metrics(self) -> dict:
        query = """
        SELECT
            COUNT(*) as total,
            COALESCE(AVG(CASE WHEN status = 'completed' THEN 1 ELSE 0 END), 0) as answer_rate
        FROM call_logs
        WHERE created_at >= CURRENT_DATE
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query)
            return {"total": row["total"], "answer_rate": float(row["answer_rate"])}


db_service = DatabaseService()
```

### Step 3.4 — Create `services/auth.py`

Extract JWT logic from `ui_server.py` lines 54-61, 300-350.

```python
"""JWT authentication service."""

import hashlib
import time
from typing import Optional

import jwt as pyjwt

from app.config import settings
from app.config.constants import JWT_ALGORITHM, JWT_EXPIRY_HOURS


class AuthService:
    def verify_login(self, username: str, password: str) -> bool:
        username_hash = hashlib.sha256(username.encode()).hexdigest()
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        return (
            username_hash == settings.ADMIN_USERNAME_HASH
            and password_hash == settings.ADMIN_PASSWORD_HASH
        )

    def create_token(self) -> str:
        now = time.time()
        payload = {
            "sub": "admin",
            "iat": now,
            "exp": now + (JWT_EXPIRY_HOURS * 3600),
        }
        return pyjwt.encode(payload, settings.JWT_SECRET, algorithm=JWT_ALGORITHM)

    def verify_token(self, token: str) -> Optional[dict]:
        try:
            return pyjwt.decode(token, settings.JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except pyjwt.PyJWTError:
            return None


auth_service = AuthService()
```

### Step 3.5 — Create `services/webhook.py`

Extract HMAC-signed delivery from `utils.py`.

```python
"""Webhook delivery service — HMAC-signed POST to MantraAssist backend."""

import asyncio
import hashlib
import hmac
import json
import time

import httpx

from app.config import settings


class WebhookService:
    async def send(
        self,
        payload: dict,
        endpoint: str = "/webhooks/n8n",
        max_retries: int = 3,
    ) -> bool:
        url = f"{settings.MANTRAASSIST_BACKEND_URL.rstrip('/')}{endpoint}"
        timestamp = str(int(time.time()))
        body = json.dumps(payload)

        signature = hmac.new(
            settings.MANTRAASSIST_WEBHOOK_SECRET.encode(),
            f"{timestamp}.{body}".encode(),
            hashlib.sha256,
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "x-signature": signature,
            "x-timestamp": timestamp,
        }

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(url, content=body, headers=headers)
                    if resp.is_success:
                        return True
            except Exception:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # exponential backoff
        return False


webhook_service = WebhookService()
```

### Step 3.6 — Create `services/s3.py`

Extract S3 recording upload from `utils.py`.

```python
"""S3 recording storage service."""

from io import BytesIO
from typing import Optional

import boto3

from app.config import settings


class S3Service:
    def __init__(self):
        self._client = None

    def start(self):
        if not settings.AWS_S3_BUCKET_NAME:
            return  # silently skip if not configured
        self._client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )

    @property
    def enabled(self) -> bool:
        return self._client is not None and bool(settings.AWS_S3_BUCKET_NAME)

    async def upload_recording(self, call_id: str, audio_bytes: bytes) -> Optional[str]:
        if not self.enabled:
            return None
        key = f"recordings/{call_id}.mp3"
        try:
            self._client.upload_fileobj(
                BytesIO(audio_bytes),
                settings.AWS_S3_BUCKET_NAME,
                key,
                ExtraArgs={"ContentType": "audio/mpeg"},
            )
            return f"https://{settings.AWS_S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"
        except Exception:
            return None


s3_service = S3Service()
```

### Step 3.7 — Create `services/sip.py`

Extract SIP call placement and provider resolution from `ui_server.py`.

```python
"""SIP call placement service."""

from typing import Optional

from app.config import settings
from app.config.constants import SIP_DEFAULT_ADDRESS_TWILIO, SIP_DEFAULT_ADDRESS_ZADARMA
from app.models.sip import SIP_ERROR_MAP, SipError, SipProvider
from app.services.livekit import livekit_service
from app.services.redis import redis_service


class SipService:
    async def place_call(
        self,
        provider: str,
        phone_number: str,
        room_name: str,
        trunk_id: str = "",
    ) -> dict:
        """Place an outbound SIP call. Returns dict with status and error info."""
        if not trunk_id:
            trunk_id = self._resolve_trunk_id(provider)

        client = livekit_service.get_client_for_provider(provider)

        status = "ringing"
        error = None

        try:
            await livekit_service.create_sip_participant(
                room_name=room_name,
                sip_trunk_id=trunk_id,
                sip_number=phone_number,
            )
        except Exception as e:
            error = str(e)
            status = self._classify_error(error)

        return {"status": status, "error": error}

    async def set_sip_error_status(self, call_id: str, error: str):
        await redis_service.set_sip_error(call_id, error)

    def _resolve_trunk_id(self, provider: str) -> str:
        if provider == "twilio":
            return settings.SIP_TRUNK_ID_TWILIO or settings.SIP_TRUNK_ID
        return settings.SIP_TRUNK_ID  # zadarma, plivo, or default

    def _get_provider_from_trunk(self, trunk_id: str) -> str:
        if "twilio" in trunk_id.lower():
            return "twilio"
        if "plivo" in trunk_id.lower():
            return "plivo"
        return "zadarma"  # default

    @staticmethod
    def _classify_error(error: str) -> str:
        for code, sip_error in SIP_ERROR_MAP.items():
            if code in error.lower():
                return sip_error.value
        return SipError.INCOMPLETE.value


sip_service = SipService()
```

### Step 3.8 — Create `services/__init__.py`

```python
from .livekit import livekit_service, LiveKitService
from .redis import redis_service, RedisService
from .db import db_service, DatabaseService
from .auth import auth_service, AuthService
from .webhook import webhook_service, WebhookService
from .s3 import s3_service, S3Service
from .sip import sip_service, SipService

__all__ = [
    "livekit_service", "LiveKitService",
    "redis_service", "RedisService",
    "db_service", "DatabaseService",
    "auth_service", "AuthService",
    "webhook_service", "WebhookService",
    "s3_service", "S3Service",
    "sip_service", "SipService",
]
```

### Step 3.9 — Verification

```python
python -c "
import asyncio
from app.services.livekit import livekit_service
from app.services.auth import auth_service
from app.services.sip import sip_service
print('All services load successfully')
"
```

---

## Phase 4: Routers Layer (Days 9-11)

### Step 4.1 — Create routers, one at a time

Each router file should be <150 lines. Each extracts a subset of endpoints from `ui_server.py`.

**`app/routers/health.py`** (~20 lines)
```python
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    return {"status": "ok"}
```

**`app/routers/auth.py`** (~60 lines)
```python
from fastapi import APIRouter, HTTPException
from app.models.auth import LoginRequest, TokenResponse
from app.services.auth import auth_service

router = APIRouter(prefix="/api/v1", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    if not auth_service.verify_login(body.username, body.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = auth_service.create_token()
    return TokenResponse(token=token)
```

**`app/routers/webhooks.py`** (~120 lines)
```python
import json
from fastapi import APIRouter, Request
from app.models.call import WebhookPayload
from app.services.livekit import livekit_service
from app.services.redis import redis_service
from app.services.sip import sip_service

router = APIRouter(prefix="/api/v1/call", tags=["webhooks"])


@router.post("/inbound")
async def inbound_webhook(request: Request):
    body = await request.json()
    payload = WebhookPayload(**body)
    
    # Create dispatch entry
    await redis_service.push_pending(body)
    
    # Trigger SIP call in background
    # (full implementation follows original webhook_handler logic)
    
    return {"status": "queued", "call_id": payload.call_id}
```

**`app/routers/sip.py`** (~130 lines)
```python
from fastapi import APIRouter
from app.services.sip import sip_service

router = APIRouter(prefix="/api/v1/sip", tags=["sip"])

# SIP trunk endpoints — one per provider
# Extracted from ui_server.py: POST /api/v1/sip/trunks/outbound/{provider}
```

**`app/routers/dashboard.py`** (~150 lines)
```python
from fastapi import APIRouter, Depends
from app.services.db import db_service
from app.services.redis import redis_service

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

# Metrics, active calls, SSE stream, call history
# Extracted from ui_server.py dashboard endpoints
```

**`app/routers/kb.py`** (~120 lines)
```python
from fastapi import APIRouter, UploadFile
from app.models.kb import IngestRequest
from app.kb.engine import kb_engine

router = APIRouter(prefix="/api/v1/kb", tags=["kb"])

# Ingest, search, delete, chat endpoints
# Extracted from ui_server.py KB endpoints
```

**`app/routers/dispatch.py`** (~60 lines)
```python
from fastapi import APIRouter
from app.services.livekit import livekit_service
from app.services.redis import redis_service

router = APIRouter(tags=["dispatch"])

# POST /dispatch-test — for test console
# Extracted from ui_server.py
```

### Step 4.2 — Create `app/main.py`

This is the new FastAPI entrypoint. It replaces `ui_server.py`.

```python
"""FastAPI application factory — replaces mantra/ui_server.py."""

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config.logging import setup_logger
from app.routers import auth, dashboard, dispatch, health, kb, sip, webhooks
from app.services import db_service, livekit_service, redis_service
from app.services.s3 import s3_service

load_dotenv(".env.local")

logger = setup_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting services...")
    await livekit_service.start()
    await redis_service.start()
    await db_service.start()
    s3_service.start()
    logger.info("All services started")
    yield
    logger.info("Shutting down services...")
    await livekit_service.stop()
    await redis_service.stop()
    await db_service.stop()
    logger.info("All services stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="Mantra Voice Agent", version="0.1.0", lifespan=lifespan)

    # ── Routers ────────────────────────────────────────────────────────
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(webhooks.router)
    app.include_router(sip.router)
    app.include_router(dashboard.router)
    app.include_router(kb.router)
    app.include_router(dispatch.router)

    # ── Static files ───────────────────────────────────────────────────
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app


app = create_app()


def main():
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8081, reload=True)


if __name__ == "__main__":
    main()
```

### Step 4.3 — Verification

```bash
python -c "from app.main import app; print('App created:', app.title)"
uvicorn app.main:app --port 8081  # should start and respond to /health
```

---

## Phase 5: Agent Subsystem (Days 12-16)

### Step 5.1 — Create `agent/entrypoint.py`

```python
"""Voice agent entrypoint — connects to LiveKit and runs the pipeline."""

import asyncio
from typing import Any

from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli, llm
from livekit.agents.voice import Agent

from app.agent.context import resolve_inbound_context, build_kb_scope
from app.agent.pipeline import create_pipeline
from app.agent.safety import SafetyMonitor
from app.agent.session import SessionManager
from app.agent.finalize import Finalizer
from app.config.logging import setup_logger
from app.config.settings import settings

logger = setup_logger("app.agent")


async def entrypoint(job: JobContext):
    logger.info(f"Agent started for room: {job.room.name}")

    # Parse metadata
    metadata: dict[str, Any] = json.loads(job.room.metadata or "{}")
    call_id = metadata.get("call_id", job.room.name)

    # Resolve KB context
    context_info = await resolve_inbound_context(metadata.get("client_phone", ""))
    kb_scope = build_kb_scope(context_info, metadata)

    # Create pipeline
    agent = Agent(
        vad=create_vad(),
        stt=create_stt(),
        llm=create_llm(metadata),
        tts=create_tts(metadata),
        turn_detector=create_turn_detector(),
    )

    # Register tools
    from app.agent.tools import get_agent_tools
    agent.register_tools(get_agent_tools(kb_scope))

    # Setup session
    session = SessionManager(agent, job.room, call_id, kb_scope)

    # Setup safety monitors
    safety = SafetyMonitor(session)
    safety.start()

    # Connect and run
    await agent.start(job.room)
    await agent.wait_for_disconnect()

    # Finalize
    finalizer = Finalizer(call_id, session.chat_history)
    await finalizer.run()
    safety.stop()


def run_agent():
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="mantra-voice-agent",
        )
    )
```

### Step 5.2 — Create `agent/pipeline.py`

Extract STT/LLM/TTS/VAD/turn detector setup from `agent.py` lines ~100-250.

```python
"""Voice pipeline assembly — STT → LLM → TTS."""

from typing import Any

from livekit.agents.voice import Agent
from livekit.plugins import deepgram, openai, google, silero, turn_detector
from livekit.plugins.cartesia import CartesiaTTS

from app.config import settings
from app.config.constants import VOICE_MAP, DEFAULT_VOICE_ID


def create_vad():
    return silero.VAD(
        min_speech_duration=0.08,
        min_silence_duration=0.15,
    )


def create_stt():
    return deepgram.STT(
        model="nova-3",
        language="hi",  # Hinglish bilingual
        api_key=settings.DEEPGRAM_API_KEY,
    )


def create_llm(metadata: dict[str, Any]) -> Any:
    """Create LLM based on metadata ai_payload.ai_model field."""
    ai_payload = metadata.get("ai_payload", {})
    model_name = ai_payload.get("ai_model", "openai")

    if model_name == "gemini":
        return google.LLM(
            model="gemini-2.5-flash",
            api_key=settings.GEMINI_API_KEY,
        )
    elif model_name == "deepseek":
        return openai.LLM(
            model="deepseek-chat",
            base_url="https://api.deepseek.com/v1",
            api_key=settings.DEEPSEEK_API_KEY,
        )
    else:  # default: openai
        return openai.LLM(
            model="gpt-4o-mini",
            api_key=settings.OPENAI_API_KEY,
        )


def create_tts(metadata: dict[str, Any]) -> Any:
    """Create TTS with FallbackAdapter for rate limit resilience."""
    ai_payload = metadata.get("ai_payload", {})
    voice_name = ai_payload.get("voice_id", "arushi")
    voice_id = VOICE_MAP.get(voice_name, DEFAULT_VOICE_ID)

    return CartesiaTTS(
        model="sonic-3",
        voice=voice_id,
        api_key=settings.CARTESIA_API_KEY,
        # FallbackAdapter implemented using multiple API keys
    )


def create_turn_detector():
    return turn_detector.MultilingualModel()
```

### Step 5.3 — Create `agent/session.py`

Extract room connection, participant events, chat context, metadata handling from `agent.py`.

```python
"""Session lifecycle management."""

import json
import time
from typing import Any, Optional

from livekit import rtc
from livekit.agents.voice import Agent

from app.config.logging import setup_logger

logger = setup_logger("app.agent.session")


class SessionManager:
    """Manages a single voice agent session."""

    def __init__(
        self,
        agent: Agent,
        room: rtc.Room,
        call_id: str,
        kb_scope: Optional[dict] = None,
    ):
        self.agent = agent
        self.room = room
        self.call_id = call_id
        self.kb_scope = kb_scope or {}
        self.chat_history: list[dict] = []
        self.started_at: float = time.time()
        self.user_joined: bool = False
        self.user_spoke: bool = False
        self.handoff_triggered: bool = False
        self.call_ended: bool = False

    def add_message(self, role: str, message: str):
        self.chat_history.append({"role": role, "message": message})

    @property
    def duration_seconds(self) -> int:
        return int(time.time() - self.started_at)
```

### Step 5.4 — Create `agent/context.py`

Extract `resolve_inbound_context()` and KB scope building from `agent.py`.

```python
"""Inbound call context resolution — phone number → org, KB, prompt."""

import json
import logging
import os
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger("app.agent.context")


async def resolve_inbound_context(
    phone_number: str,
) -> dict[str, Any]:
    """Resolve inbound call context from backend API or local fallback."""
    if settings.LOCAL_INBOUND_MAPPINGS:
        return _load_local_mappings(phone_number)

    try:
        url = f"{settings.MANTRAASSIST_BACKEND_URL}/api/v1/telephony/resolve-inbound-call"
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(url, json={"phone_number": phone_number})
            if resp.is_success:
                return resp.json()
    except Exception as e:
        logger.warning(f"Backend resolve failed, using local fallback: {e}")

    return _load_local_mappings(phone_number)


def build_kb_scope(
    context_info: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Build KB scope from resolved context and call metadata."""
    kb_ids: list[str] = []
    kb_tags: list[str] = []

    org_id = context_info.get("org_id") or metadata.get("org_id", "")
    kb_id = context_info.get("kb_id") or metadata.get("kb_id", "")
    payload_kb_ids = metadata.get("kb_ids", [])
    payload_kb_tags = metadata.get("kb_tags", [])

    if org_id:
        kb_ids.append(org_id)
    if kb_id:
        kb_ids.append(kb_id)
    kb_ids.extend(payload_kb_ids)
    kb_tags.extend(payload_kb_tags)

    return {
        "kb_ids": list(set(kb_ids)),
        "kb_tags": list(set(kb_tags)),
        "prompt": context_info.get("prompt") or metadata.get("prompt", ""),
        "voice": context_info.get("voice") or metadata.get("ai_payload", {}).get("voice_id", "arushi"),
        "model": context_info.get("model") or metadata.get("ai_payload", {}).get("ai_model", "openai"),
        "transfer_numbers": context_info.get("transfer_numbers", {}),
    }


def _load_local_mappings(phone_number: str) -> dict[str, Any]:
    """Fallback: load inbound mappings from local JSON file."""
    path = os.path.join(
        os.path.dirname(__file__), "..", "..", "config", "inbound_mappings.json"
    )
    try:
        with open(path) as f:
            mappings = json.load(f)
        for mapping in mappings.get("mappings", []):
            if phone_number in mapping.get("phone_numbers", []):
                return mapping
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Local mappings not found: {e}")
    return {}
```

### Step 5.5 — Create `agent/handoff.py`

Extract `transfer_to_human` orchestration from `agent.py` lines 279-378.

```python
"""Human handoff orchestration."""

from typing import Optional

from app.config import settings
from app.config.constants import TRANSFER_DEFAULT_NUMBER, TRANSFER_NUMBERS
from app.services.livekit import livekit_service
from app.services.webhook import webhook_service
from app.config.logging import setup_logger

logger = setup_logger("app.agent.handoff")


async def transfer_to_human(
    room_name: str,
    call_id: str,
    department: str = "general",
    transfer_numbers_override: Optional[dict[str, str]] = None,
) -> str:
    """Transfer call to a human agent via SIP."""
    numbers = transfer_numbers_override or TRANSFER_NUMBERS
    target_number = numbers.get(department, TRANSFER_DEFAULT_NUMBER)

    trunk_id = settings.SIP_TRUNK_ID
    if not trunk_id:
        logger.error("No SIP trunk configured for handoff")
        return "HANDOFF_FAILED: No SIP trunk configured"

    try:
        await livekit_service.create_sip_participant(
            room_name=room_name,
            sip_trunk_id=trunk_id,
            sip_number=target_number,
        )
        logger.info(f"Handoff: dialed {target_number} into room {room_name}")
    except Exception as e:
        logger.error(f"Handoff SIP failed: {e}")
        return f"HANDOFF_FAILED: {e}"

    # Send webhook
    await webhook_service.send(
        {
            "event": "HANDOFF_REQUESTED",
            "call_id": call_id,
            "department": department,
            "target_number": target_number,
        }
    )

    return "TRANSFER_COMPLETE. Do not speak."
```

### Step 5.6 — Create `agent/finalize.py`

Extract post-call processing from `agent.py` lines 711-951.

```python
"""Post-call finalization — recording, analysis, webhook, DB."""

import json
from typing import Any, Optional

from app.config.logging import setup_logger
from app.services.db import db_service
from app.services.s3 import s3_service
from app.services.webhook import webhook_service
from app.services.redis import redis_service
from app.llm.analyze import analyze_call

logger = setup_logger("app.agent.finalize")


async def finalize(
    call_id: str,
    chat_history: list[dict],
    audio_bytes: Optional[bytes] = None,
    sip_error: Optional[str] = None,
    metadata: Optional[dict] = None,
    kb_scope: Optional[dict] = None,
):
    """Run post-call processing pipeline."""
    metadata = metadata or {}
    kb_scope = kb_scope or {}

    # 1. Upload recording
    recording_url = None
    if audio_bytes:
        recording_url = await upload_recording(call_id, audio_bytes)

    # 2. Build transcript
    transcript = build_transcript(chat_history)

    # 3. Analyze call
    analysis = await analyze_call(transcript)

    # 4. Determine status
    status = determine_status(sip_error, metadata)

    # 5. Build webhook payload
    webhook_payload = build_webhook_payload(
        call_id=call_id,
        status=status,
        transcript=transcript,
        analysis=analysis,
        recording_url=recording_url,
        metadata=metadata,
        kb_scope=kb_scope,
    )

    # 6. Send webhook
    await webhook_service.send(webhook_payload)

    # 7. Save to DB
    await db_service.save_call_log(
        call_id=call_id,
        call_log=json.dumps(transcript),
        status=status,
        recording_url=recording_url or "",
    )

    # 8. Free Redis capacity
    await redis_service.remove_active(call_id)


async def upload_recording(call_id: str, audio_bytes: bytes) -> Optional[str]:
    if s3_service.enabled:
        return await s3_service.upload_recording(call_id, audio_bytes)
    return None


def build_transcript(chat_history: list[dict]) -> list[dict]:
    return [
        {"role": msg.get("role", "user"), "message": msg.get("message", "")}
        for msg in chat_history
    ]


def determine_status(sip_error: Optional[str], metadata: dict) -> str:
    if sip_error:
        return sip_error
    if metadata.get("user_joined"):
        return "completed"
    return "no_answer"


def build_webhook_payload(**kwargs) -> dict:
    return {
        "event": "CALL_COMPLETED",
        "call_id": kwargs["call_id"],
        "status": kwargs["status"],
        "transcript": kwargs["transcript"],
        "analysis": kwargs["analysis"],
        "recording_url": kwargs["recording_url"] or "",
        "direction": kwargs.get("metadata", {}).get("direction", "outbound"),
        "inbound_context": {
            "org_id": kwargs.get("kb_scope", {}).get("kb_ids", [None])[0],
            "kb_id": kwargs.get("kb_scope", {}).get("kb_ids", []),
        },
    }
```

### Step 5.7 — Create `agent/safety.py`

Extract inactivity monitor, farewell detection, call limiter from `agent.py`.

```python
"""Safety monitors — inactivity, farewell, call duration limits."""

import asyncio
from typing import Optional

from app.config import settings
from app.config.constants import CALL_DURATION_LIMIT_SECONDS, FAREWELL_PHRASES, INACTIVITY_TIMEOUT_SECONDS
from app.config.logging import setup_logger

logger = setup_logger("app.agent.safety")


class SafetyMonitor:
    """Monitors call health and enforces limits."""

    def __init__(self, session_manager):
        self.session = session_manager
        self._tasks: list[asyncio.Task] = []

    def start(self):
        self._tasks = [
            asyncio.create_task(self._inactivity_monitor()),
            asyncio.create_task(self._call_limiter()),
        ]

    def stop(self):
        for task in self._tasks:
            task.cancel()

    def reset_inactivity(self):
        """Called when user speaks — resets the inactivity timer."""

    async def _inactivity_monitor(self):
        """Disconnect after INACTIVITY_TIMEOUT_SECONDS of no response."""
        await asyncio.sleep(INACTIVITY_TIMEOUT_SECONDS)
        if not self.session.user_spoke:
            logger.info("Inactivity timeout — disconnecting")
            await self.session.agent.disconnect()

    async def _call_limiter(self):
        """Hard limit on call duration."""
        await asyncio.sleep(CALL_DURATION_LIMIT_SECONDS)
        logger.info("Call duration limit reached — disconnecting")
        await self.session.agent.disconnect()

    @staticmethod
    def is_farewell(text: str) -> bool:
        """Check if user said goodbye."""
        lower = text.lower().strip()
        return any(phrase in lower for phrase in FAREWELL_PHRASES)
```

### Step 5.8 — Create `agent/tools/`

**`agent/tools/__init__.py`**
```python
"""Central tool registry — add new tools here."""

from typing import Any

from .search_kb import search_knowledge_base
from .handoff import transfer_to_human as transfer_to_human_tool
from .end_call import end_call

__all__ = [
    "search_knowledge_base",
    "transfer_to_human",
    "end_call",
    "get_agent_tools",
]


def get_agent_tools(kb_scope: dict[str, Any] = None):
    tools = [
        search_knowledge_base,
        transfer_to_human_tool,
        end_call,
    ]
    return tools
```

**`agent/tools/search_kb.py`** (~50 lines)
```python
from livekit.agents import llm
from app.kb.retriever import kb_retriever


@llm.tool
async def search_knowledge_base(
    context: llm.ToolContext,
    query: str,
) -> str:
    """Search the knowledge base for relevant information.
    
    Call this when you need factual information about services,
    treatments, pricing, or policies.
    
    Args:
        query: The search query string
    """
    # Get KB scope from context metadata
    metadata = context.metadata or {}
    kb_ids = metadata.get("kb_ids", [])
    kb_tags = metadata.get("kb_tags", [])

    if not kb_ids:
        return "No Knowledge Base configured for this session."

    return await kb_retriever.retrieve(
        query=query,
        kb_ids=kb_ids,
        top_k=3,
        tags=kb_tags,
    )
```

**`agent/tools/handoff.py`** (~30 lines)
```python
from livekit.agents import llm
from app.agent.handoff import transfer_to_human as handoff_orchestrator


@llm.tool
async def transfer_to_human(
    context: llm.ToolContext,
    department: str = "general",
) -> str:
    """Transfer the caller to a human agent.
    
    Call this when the user asks to speak to a human, or when you
    cannot resolve their issue.
    
    Args:
        department: The department to transfer to (support, billing, refund, general)
    """
    metadata = context.metadata or {}
    room_name = metadata.get("room_name", "")
    call_id = metadata.get("call_id", "")
    transfer_numbers = metadata.get("transfer_numbers", {})

    return await handoff_orchestrator(
        room_name=room_name,
        call_id=call_id,
        department=department,
        transfer_numbers_override=transfer_numbers or None,
    )
```

**`agent/tools/end_call.py`** (~20 lines)
```python
from livekit.agents import llm


@llm.tool
async def end_call(context: llm.ToolContext) -> str:
    """End the current call gracefully.
    
    Call this when the conversation is naturally complete or the
    user has said goodbye.
    """
    # The agent framework handles the actual disconnect via return
    return "Call ended. Goodbye."
```

### Step 5.9 — Verification

```python
python -c "
from app.agent.tools import get_agent_tools
tools = get_agent_tools()
print(f'{len(tools)} tools registered')
for t in tools:
    print(f'  - {t}')
"
```

---

## Phase 6: Dispatcher + Routines (Days 17-18)

### Step 6.1 — Create `dispatcher/worker.py`

Extract `dispatch_call()` and queue management from `dispatcher.py`.

```python
"""Call dispatcher — handles dispatch of a single call."""

import json
import logging

from app.config import settings
from app.services.livekit import livekit_service

logger = logging.getLogger("app.dispatcher.worker")


async def dispatch_call(payload: dict) -> bool:
    """Dispatch a single call to LiveKit. Returns True on success."""
    call_id = payload.get("call_id") or payload.get("voice_id")
    room_name = payload.get("_resolved_room_name", f"call_{call_id}")
    phone_number = payload.get("_resolved_phone_number")
    trunk_id = payload.get("_resolved_trunk_id")

    if not phone_number:
        logger.error(f"No phone number for call {call_id}")
        return False

    try:
        await livekit_service.create_room(room_name)
        await livekit_service.create_sip_participant(
            room_name=room_name,
            sip_trunk_id=trunk_id,
            sip_number=phone_number,
        )
        return True
    except Exception as e:
        logger.error(f"Dispatch failed for {call_id}: {e}")
        await livekit_service.delete_room(room_name)
        return False
```

### Step 6.2 — Create `dispatcher/capacity.py`

```python
"""Capacity checks for the dispatcher."""

from app.config import settings


async def has_capacity(active_count: int) -> bool:
    """Check if we can accept more calls."""
    limits = [
        settings.MAX_CONCURRENCY,
        settings.LIVEKIT_MAX_ROOMS,
        settings.AGENT_MAX_WORKERS,
    ]
    effective_limit = min(limits)
    return active_count < effective_limit
```

### Step 6.3 — Create `routines/dispatcher_loop.py`

Extract the main polling loop from `dispatcher.py`.

```python
"""Dispatcher background loop — polls Redis queue and dispatches calls."""

import asyncio
import json
import logging
import time

from app.dispatcher.capacity import has_capacity
from app.dispatcher.worker import dispatch_call
from app.services.redis import redis_service

logger = logging.getLogger("app.routines.dispatcher")


async def dispatcher_loop(interval: float = 0.5):
    """Main dispatcher loop — runs forever."""
    logger.info("Dispatcher loop started")

    while True:
        try:
            await _process_next_call()
        except Exception as e:
            logger.error(f"Dispatcher error: {e}", exc_info=True)

        await asyncio.sleep(interval)


async def _process_next_call():
    """Pop and process the next pending call."""
    active_count = await redis_service.active_count()

    if not await has_capacity(active_count):
        return

    payload = await redis_service.pop_pending()
    if not payload:
        return

    logger.info(f"Dispatching call {payload.get('call_id')}")
    success = await dispatch_call(payload)

    if not success:
        logger.warning(f"Re-queuing call {payload.get('call_id')}")
        await redis_service.requeue(payload)
```

### Step 6.4 — Create `routines/zombie_cleanup.py`

Extract zombie room cleanup logic.

```python
"""Zombie cleanup — reconciles Redis active calls with LiveKit rooms."""

import asyncio
import logging

from app.services.livekit import livekit_service
from app.services.redis import redis_service

logger = logging.getLogger("app.routines.zombie_cleanup")


async def zombie_cleanup(interval: float = 60):
    """Periodically clean up stale rooms from Redis."""
    while True:
        try:
            await _run_cleanup()
        except Exception as e:
            logger.error(f"Zombie cleanup error: {e}")

        await asyncio.sleep(interval)


async def _run_cleanup():
    active_calls = await redis_service.all_active()
    livekit_rooms = await livekit_service.list_rooms()
    livekit_room_names = {r.name for r in livekit_rooms}

    for call in active_calls:
        room_name = call.get("room_name", "")
        call_id = call.get("call_id", "")
        if room_name and room_name not in livekit_room_names:
            logger.info(f"Cleaning up zombie: {call_id} in room {room_name}")
            await redis_service.remove_active(call_id)
```

---

## Phase 7: KB Engine (Days 19-20)

### Step 7.1 — Create `kb/engine.py`

Extract `PostgresKnowledgeBase` from `knowledge_base.py`.

```python
"""Knowledge base engine — PostgreSQL FTS-based search and ingestion."""

import logging
from typing import Optional

import asyncpg

from app.services.db import db_service

logger = logging.getLogger("app.kb.engine")


def build_search_query(use_generated_column: bool = True) -> str:
    vector_expr = "text_search" if use_generated_column else "to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(content_in_text, ''))"
    return f"""
        SELECT id, kb_id, title, content, source_type, page_meta, content_in_text, created_at,
               ts_rank({vector_expr}, websearch_to_tsquery('simple', $2)) as similarity
        FROM kb_pages
        WHERE kb_id = ANY($1::text[])
          AND {vector_expr} @@ websearch_to_tsquery('simple', $2)
          AND ($4::text[] IS NULL OR
              (jsonb_typeof(page_meta->'tags_name') = 'array' AND page_meta->'tags_name' ?| $4::text[]) OR
              (jsonb_typeof(page_meta->'tags_name') = 'string' AND page_meta->>'tags_name' = ANY($4::text[]))
          )
        ORDER BY similarity DESC
        LIMIT $3
    """


class PostgresKnowledgeBase:
    def __init__(self):
        self._search_query = build_search_query()

    async def search(
        self,
        kb_ids: list[str],
        query: str,
        top_k: int = 3,
        tags: Optional[list[str]] = None,
    ) -> list[dict]:
        async with db_service.pool.acquire() as conn:
            rows = await conn.fetch(
                self._search_query,
                kb_ids,
                query,
                top_k,
                tags,
            )
            return [dict(r) for r in rows]

    async def add_page(
        self,
        kb_id: str,
        title: str,
        content: str,
        content_in_text: str,
        source_type: str,
        page_meta: Optional[dict] = None,
    ) -> str:
        import uuid
        page_id = str(uuid.uuid4())
        query = """
        INSERT INTO kb_pages (id, kb_id, title, content, content_in_text, source_type, page_meta)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """
        async with db_service.pool.acquire() as conn:
            await conn.execute(query, page_id, kb_id, title, content, content_in_text, source_type, page_meta or {})
        return page_id

    async def delete_by_document(self, kb_id: str, document_id: str):
        query = "DELETE FROM kb_pages WHERE kb_id = $1 AND page_meta->>'document_id' = $2"
        async with db_service.pool.acquire() as conn:
            await conn.execute(query, kb_id, document_id)


kb_engine = PostgresKnowledgeBase()
```

### Step 7.2 — Create `kb/chunker.py`

Extract the adaptive chunker from `knowledge_base.py`.

```python
"""Adaptive document chunker — heading, paragraph, or sliding-window."""

import re
from typing import Any


def chunk_document(
    text: str,
    title: str = "",
    max_chunk_size: int = 1000,
) -> list[dict[str, Any]]:
    """Adaptively chunk a document based on its structure."""
    chunks = []
    
    # Try heading-based chunking first
    heading_chunks = _chunk_by_headings(text, max_chunk_size)
    if heading_chunks:
        return _tag_chunks(heading_chunks, "heading", title)

    # Try paragraph-based
    para_chunks = _chunk_by_paragraphs(text, max_chunk_size)
    if para_chunks:
        return _tag_chunks(para_chunks, "paragraph", title)

    # Fallback: sliding window
    window_chunks = _chunk_by_sliding_window(text, max_chunk_size)
    return _tag_chunks(window_chunks, "sliding_window", title)


def _chunk_by_headings(text: str, max_size: int) -> list[str]:
    pattern = r'(?:^|\n)(#{1,3}\s+.*?(?:\n|$))'
    sections = re.split(pattern, text, flags=re.MULTILINE)
    # ... full implementation follows original knowledge_base.py
    return []


def _chunk_by_paragraphs(text: str, max_size: int) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks, current = [], ""
    for para in paragraphs:
        if len(current) + len(para) < max_size:
            current += "\n\n" + para
        else:
            if current:
                chunks.append(current.strip())
            current = para
    if current:
        chunks.append(current.strip())
    return chunks


def _chunk_by_sliding_window(text: str, max_size: int) -> list[str]:
    words = text.split()
    chunks, current = [], []
    current_len = 0
    for word in words:
        if current_len + len(word) + 1 > max_size and current:
            chunks.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len += len(word) + 1
    if current:
        chunks.append(" ".join(current))
    return chunks


def _tag_chunks(chunks: list[str], strategy: str, title: str) -> list[dict[str, Any]]:
    return [
        {
            "title": f"{title} (part {i+1})" if len(chunks) > 1 else title,
            "content": chunk,
            "meta": {"chunking_strategy": strategy, "chunk_index": i},
        }
        for i, chunk in enumerate(chunks)
    ]
```

### Step 7.3 — Move `retriever.py` to `kb/retriever.py`

The existing `mantra/retriever.py` is already clean. Just move it:

```python
"""Knowledge retriever with in-memory session cache."""

import logging
from typing import Optional

from app.kb.engine import kb_engine

logger = logging.getLogger("app.kb.retriever")


class KnowledgeRetriever:
    def __init__(self):
        self.session_cache: dict[str, str] = {}

    async def retrieve(
        self,
        query: str,
        kb_ids: list[str],
        top_k: int = 3,
        tags: Optional[list[str]] = None,
    ) -> str:
        if not kb_ids:
            return "No Knowledge Base configured for this session."

        cache_key = self._make_cache_key(query, kb_ids, tags)
        if cache_key in self.session_cache:
            logger.info(f"Cache hit for: '{query}'")
            return self.session_cache[cache_key]

        results = await kb_engine.search(
            kb_ids=kb_ids,
            query=query,
            top_k=top_k,
            tags=tags,
        )

        if not results:
            formatted = "No relevant information found in the knowledge base for this query."
        else:
            formatted = "--- RELEVANT KNOWLEDGE BASE INFORMATION ---\n\n"
            for i, r in enumerate(results, 1):
                formatted += f"Source {i} [{r['title']}]:\n{r['content_in_text']}\n\n"

        self.session_cache[cache_key] = formatted
        return formatted

    def clear_cache(self):
        self.session_cache.clear()

    @staticmethod
    def _make_cache_key(query: str, kb_ids: list[str], tags: Optional[list[str]]) -> str:
        import hashlib
        raw = f"{query.strip().lower()}|{sorted(kb_ids)}|{sorted(tags or [])}"
        return hashlib.md5(raw.encode()).hexdigest()


kb_retriever = KnowledgeRetriever()
```

### Step 7.4 — Create `kb/migration.py`

Extract DDL from `knowledge_base.py`.

```python
"""KB schema management."""

KB_PAGES_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS kb_pages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kb_id           TEXT NOT NULL,
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,
    source_type     TEXT NOT NULL,
    page_meta       JSONB DEFAULT '{}',
    content_in_text TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    text_search     tsvector GENERATED ALWAYS AS (
                        to_tsvector('english', coalesce(title, '') || ' ' || coalesce(content_in_text, ''))
                    ) STORED
);
CREATE INDEX IF NOT EXISTS idx_kb_pages_kb_id ON kb_pages (kb_id);
CREATE INDEX IF NOT EXISTS idx_kb_pages_fts ON kb_pages USING GIN (text_search);
"""
```

---

## Phase 8: Tests + Cleanup (Days 21-25)

### Step 8.1 — Create test scaffold

**`tests/conftest.py`**
```python
"""Shared test fixtures."""

import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def redis_service():
    from app.services.redis import RedisService
    svc = RedisService()
    await svc.start()
    yield svc
    await svc.stop()


@pytest_asyncio.fixture
async def db_service():
    from app.services.db import DatabaseService
    svc = DatabaseService()
    await svc.start()
    yield svc
    await svc.stop()
```

### Step 8.2 — Write critical path tests

**`tests/test_services/test_sip.py`**
**`tests/test_agent/test_safety.py`**
**`tests/test_routers/test_webhooks.py`**
**`tests/test_kb/test_chunker.py`**
**`tests/test_kb/test_engine.py`**

### Step 8.3 — Update pyproject.toml

```toml
[project.scripts]
mantra-agent = "app.agent.entrypoint:run_agent"
mantra-ui = "app.main:main"

[tool.setuptools.packages.find]
where = ["."]
include = ["app*"]
exclude = ["mantra*", "static*", "recordings*", "massist*"]
```

### Step 8.4 — Update entrypoint.sh

```bash
#!/bin/bash
case "${MODE:-agent}" in
  agent)  exec uv run python -m app.agent.entrypoint ;;
  ui)     exec uv run python -m app.main ;;
  mcp)    exec uv run python mcp/server.py ;;
  *)      echo "Unknown MODE: $MODE"; exit 1 ;;
esac
```

### Step 8.5 — Delete old files

```bash
# Only do this after verifying everything works in production
rm -rf mantra/
```

### Step 8.6 — Update vault docs

Update `obsidian/`:
- `Home.md` — update stats, remove mantra/ references
- `Architecture/Overview.md` — update process table, file sizes
- `Context/Repository Map.md` — new tree, new line counts
- `Features/*.md` — update file references to new paths
- Mark `Restructure Plan.md` status as "Completed"

---

## Rollback Plan

If something breaks at any phase, the restore is trivial because `mantra/` is never touched until the very end:

```bash
# 1. Switch entrypoints back to old code
git checkout -- pyproject.toml entrypoint.sh Dockerfile

# 2. The old mantra/ package is still there and importable
python -c "from mantra.ui_server import app; print('Old app OK')"

# 3. Debug and fix the new app/ code
# 4. Switch back when ready
```

---

## Verification Checklist at Each Phase

| Phase | Command | Expected |
|-------|---------|----------|
| 1 | `python -c "from app.config.settings import settings"` | No import errors |
| 2 | `python -c "from app.models.call import CallMetadata"` | No import errors |
| 3 | `python -c "from app.services import livekit_service"` | No import errors |
| 4 | `uvicorn app.main:app --port 8081` | Server starts, `/health` returns 200 |
| 5 | `python -c "from app.agent.tools import get_agent_tools"` | Tools list returned |
| 6 | `python -c "from app.routines.dispatcher_loop import dispatcher_loop"` | No import errors |
| 7 | `python -c "from app.kb.engine import kb_engine"` | No import errors |
| 8 | `pytest tests/ -v` | Tests pass |
| Final | `grep -r "from mantra" app/ --include="*.py"` | No results (zero old imports) |
