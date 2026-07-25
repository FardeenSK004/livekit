# Codebase Restructure Plan

> **Status:** ✅ Completed + verified (**GO WITH CAVEATS**) — branch `feature/restructure`  
> **Last Updated:** 2026-07-25  
> **Reference Repos:** `support-bot`, `mantraback`  
> **Implementation:** [[Development/Restructure Implementation.md]] (Phases 0–8 complete; `mantra/` deleted)  
> **Verification:** [[Development/Restructure Verification Report.md]] · repo-root `report.md` (39/39 endpoint smoke; commit OK, prod after env+MCP+call)

---

## 1. Problems With Current Structure

| Problem | Current State | Impact |
|---------|---------------|--------|
| **Monolith files** | `agent.py` = 1,617 lines, `ui_server.py` = 2,863 lines | Hard to reason about, modify, or debug; merge conflicts on every change |
| **Mixed concerns** | Webhook handling, SIP trunking, dashboard APIs, KB ingestion all in `ui_server.py` | Violates Single Responsibility Principle; changes to one feature risk breaking others |
| **Global state** | `lk_client`, `plivo_client`, `redis_client` as module-level globals in `ui_server.py` | No lifecycle management; impossible to test in isolation |
| **No separation of layers** | HTTP request parsing, business logic, and DB access interleaved in same functions | Cannot swap implementations; no clear API contract |
| **Prompts in code** | System prompts, farewell phrases, guardrails hardcoded as Python strings in `agent.py` | Non-technical team members can't iterate on prompts; requires code deploy for every tweak |
| **No type safety** | No Pydantic models for request/response payloads | Runtime errors from malformed payloads; no editor autocompletion |
| **No dependency injection** | Modules import each other directly or use globals | Circular imports; impossible to mock in tests |
| **No tool registration pattern** | Tools defined as standalone functions scattered through `agent.py` | No discoverability; no metadata for service filtering or authorization |

---

## 2. Target Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        app/                                  │
│                                                              │
│  ┌─────────────┐    ┌──────────────┐    ┌────────────────┐  │
│  │  routers/    │───>│  services/   │───>│  external infra │  │
│  │  (thin HTTP) │    │  (business)  │    │  (DB, Redis,    │  │
│  │              │    │              │    │   LiveKit API,  │  │
│  │  webhooks.py │    │  livekit.py  │    │   S3, SMTP)     │  │
│  │  sip.py      │    │  redis.py    │    └────────────────┘  │
│  │  auth.py     │    │  db.py       │                         │
│  │  dashboard.py│    │  webhook.py  │    ┌────────────────┐  │
│  │  kb.py       │    │  s3.py       │    │  agent/         │  │
│  │  dispatch.py │    │  sip.py      │    │  (STT→LLM→TTS)  │  │
│  │  health.py   │    │  auth.py     │    │  tools/         │  │
│  └─────────────┘    └──────────────┘    │  handoff.py     │  │
│                                          │  finalize.py    │  │
│  ┌─────────────┐    ┌──────────────┐    │  pipeline.py    │  │
│  │  models/     │    │  config/      │    │  safety.py      │  │
│  │  (Pydantic)  │    │  (settings)   │    └────────────────┘  │
│  │              │    │              │                         │
│  │  call.py     │    │  settings.py │    ┌────────────────┐  │
│  │  agent.py    │    │  constants.py│    │  routines/      │  │
│  │  sip.py      │    │  logging.py  │    │  (background)   │  │
│  │  kb.py       │    └──────────────┘    │  dispatcher     │  │
│  │  dashboard.py│                        │  zombie_cleanup │  │
│  │  auth.py     │                        └────────────────┘  │
│  └─────────────┘                                             │
└──────────────────────────────────────────────────────────────┘
```

### Key Design Rules

1. **routers/ are thin** — parse request, validate, call service, return response. No business logic.
2. **services/ contain all logic** — reusable across routers and agents. No HTTP awareness.
3. **agent/ is self-contained** — owns the voice pipeline and LLM tools. Communicates with the outside via services/.
4. **models/ are the contract** — every function signature uses Pydantic models, not raw dicts.
5. **config/ is the single source of truth** — one `Settings` class for all env vars, one `constants.py` for all magic strings.
6. **prompts/ are files** — every prompt string lives in a `.md` file, loaded at startup.
7. **One file per concern** — not one file per function, but one file per logical domain.

---

## 3. Proposed Directory Structure

```
livekit/
│
├── app/                              # Application root (replaces mantra/)
│   ├── __init__.py
│   │
│   ├── main.py                       # FastAPI app factory + lifespan
│   │
│   ├── config/                       # Configuration layer
│   │   ├── __init__.py
│   │   ├── settings.py               # Pydantic BaseSettings — all env vars
│   │   ├── constants.py              # Magic strings: voice maps, transfer numbers, limits
│   │   └── logging.py                # Logging config, ColorFormatter
│   │
│   ├── models/                       # Pydantic schemas (the "API contract")
│   │   ├── __init__.py
│   │   ├── call.py                   # CallPayload, CallStatus, CallMetadata
│   │   ├── agent.py                  # AgentState, SessionData, ToolResult
│   │   ├── sip.py                    # SipTrunkConfig, Provider, SipParticipant
│   │   ├── kb.py                     # KnowledgePage, IngestRequest, SearchResult
│   │   ├── dashboard.py              # MetricsResponse, ActiveCall, StreamEvent
│   │   └── auth.py                   # LoginRequest, TokenResponse, TokenPayload
│   │
│   ├── routers/                      # HTTP layer — thin, no business logic
│   │   ├── __init__.py
│   │   ├── webhooks.py               # POST /api/v1/call/inbound
│   │   ├── sip.py                    # SIP trunk CRUD (/twilio, /plivo, /zadarma)
│   │   ├── auth.py                   # POST /login, token refresh
│   │   ├── dashboard.py              # GET /api/v1/dashboard/*, SSE stream
│   │   ├── kb.py                     # KB ingestion, search, deletion
│   │   ├── dispatch.py               # POST /dispatch-test
│   │   └── health.py                 # GET /health
│   │
│   ├── services/                     # Business logic layer (no HTTP awareness)
│   │   ├── __init__.py
│   │   ├── livekit.py                # LiveKit API client factory + management
│   │   ├── redis.py                  # Redis client + queue operations
│   │   ├── db.py                     # PostgreSQL connection pool + queries
│   │   ├── auth.py                   # JWT creation/verification, password hashing
│   │   ├── webhook.py                # HMAC-signed delivery to MantraAssist backend
│   │   ├── s3.py                     # S3 upload / recording storage
│   │   └── sip.py                    # SIP call placement + provider resolution
│   │
│   ├── agent/                        # Voice agent subsystem
│   │   ├── __init__.py
│   │   ├── entrypoint.py             # run_agent() — LiveKit Agent entrypoint
│   │   ├── pipeline.py               # STT→LLM→TTS pipeline assembly
│   │   ├── session.py                # Session lifecycle: join, activity, disconnect
│   │   ├── context.py                # resolve_inbound_context(), KB scope resolution
│   │   ├── handoff.py                # transfer_to_human orchestration
│   │   ├── finalize.py               # Post-call: recording, analysis, webhook, DB
│   │   ├── safety.py                 # Inactivity monitor, farewell detect, call limiter
│   │   │
│   │   └── tools/                    # LLM function tools (one file per domain)
│   │       ├── __init__.py           # Tool registration hub
│   │       ├── search_kb.py          # search_knowledge_base
│   │       ├── handoff.py            # transfer_to_human
│   │       ├── end_call.py           # end_call
│   │       └── __template.py         # Template for adding new tools
│   │
│   ├── stt/                          # Speech-to-text
│   │   ├── __init__.py
│   │   └── deepgram.py               # Deepgram Nova-3 config
│   │
│   ├── llm/                          # Language model layer
│   │   ├── __init__.py
│   │   ├── models.py                 # Model registry: openai/gemini/deepseek
│   │   └── analyze.py                # Post-call LLM analysis
│   │
│   ├── tts/                          # Text-to-speech
│   │   ├── __init__.py
│   │   └── cartesia.py               # Cartesia Sonic-3 + FallbackAdapter
│   │
│   ├── kb/                           # Knowledge base engine
│   │   ├── __init__.py
│   │   ├── engine.py                 # PostgresKnowledgeBase (search, add, delete)
│   │   ├── chunker.py                # Adaptive chunker (heading/paragraph/sliding)
│   │   ├── retriever.py              # KnowledgeRetriever with session cache
│   │   └── migration.py              # Schema bootstrap / DDL
│   │
│   ├── recording/                    # Audio recording
│   │   ├── __init__.py
│   │   └── session_recorder.py       # SessionRecorder (numpy → MP3)
│   │
│   ├── dispatcher/                   # Call dispatcher background worker
│   │   ├── __init__.py
│   │   ├── worker.py                 # dispatch_call(), queue management
│   │   └── capacity.py               # Capacity checks
│   │
│   ├── routines/                     # Background periodic tasks
│   │   ├── __init__.py
│   │   ├── dispatcher_loop.py        # Main 0.5s polling loop
│   │   └── zombie_cleanup.py         # Stale room reconciliation
│   │
│   ├── alerter/                      # Alerting subsystem
│   │   ├── __init__.py
│   │   └── email.py                  # send_crash_email() with meme support
│   │
│   └── static/                       # Frontend files (unchanged)
│       ├── index.html
│       ├── dashboard.html
│       ├── dashboard.js
│       ├── app.js
│       └── login.html
│
├── mcp/                              # MCP server (standalone process)
│   ├── __init__.py
│   └── server.py
│
├── prompts/                          # Prompt files (extracted from code)
│   ├── system.md                     # Main system prompt template
│   ├── handoff.md                    # Handoff instructions
│   ├── farewell.md                   # Farewell detection
│   ├── analysis.md                   # Post-call analysis prompt
│   └── guardrails.md                 # 5-rule factual override framework
│
├── config/                           # Runtime configuration
│   ├── inbound_mappings.json         # Local inbound mapping fallback
│   └── voices.json                   # Voice ID definitions
│
├── migrations/                       # Database migrations
│   ├── 001_create_kb_pages.sql
│   ├── 002_create_call_logs.sql
│   └── 003_create_org_configs.sql
│
├── tests/                            # Test suite (to be created)
│   ├── __init__.py
│   ├── conftest.py                   # Shared fixtures, mock clients
│   ├── test_services/
│   │   ├── test_sip.py
│   │   ├── test_webhook.py
│   │   └── test_db.py
│   ├── test_agent/
│   │   ├── test_safety.py
│   │   ├── test_handoff.py
│   │   └── test_finalize.py
│   ├── test_routers/
│   │   ├── test_webhooks.py
│   │   ├── test_sip.py
│   │   └── test_kb.py
│   └── test_kb/
│       ├── test_chunker.py
│       └── test_engine.py
│
├── docs/                             # Additional docs
│
├── pyproject.toml
├── Dockerfile
├── entrypoint.sh
├── dev.sh
├── livekit.toml
├── .env.example
├── .env.local                        # (gitignored)
│
└── obsidian/                         # Knowledge base (unchanged)
    ├── Home.md
    ├── Architecture/
    ├── Features/
    ├── Development/
    └── ...
```

---

## 4. Migration Plan

### Phase 1: Scaffold + Config (Day 1-2)

- Create `app/` directory with the full package skeleton (all `__init__.py` files)
- Create `config/settings.py` — extract every `os.getenv()` call into a Pydantic `Settings` class
- Create `config/constants.py` — extract voice maps, transfer numbers, farewell phrases, limits
- Create `config/logging.py` — extract `ColorFormatter` and logging setup
- Create `prompts/` — extract all hardcoded prompt strings from `agent.py` into `.md` files
- Create `migrations/` — extract DDL from Python strings into `.sql` files
- **Deliverable:** `app/config/` loads cleanly; all env vars are typed and validated

### Phase 2: Models Layer (Day 3-4)

- Create `models/call.py`, `models/agent.py`, `models/sip.py`, `models/kb.py`, `models/dashboard.py`, `models/auth.py`
- Define Pydantic models for every data structure currently passed as raw dicts
- **Deliverable:** Every data shape in the system has a typed model; remove all inline dict construction

### Phase 3: Services Layer (Day 5-8)

Extract business logic from `ui_server.py` into services:

| Service | Extracted From | Responsibility |
|---------|---------------|----------------|
| `services/livekit.py` | `ui_server.py` lines 44-50, 75-120, 200-280 | API client creation, room management, SIP participant creation |
| `services/redis.py` | `ui_server.py` scattered, `dispatcher.py` | Redis connection, queue push/pop, capacity tracking |
| `services/db.py` | `ui_server.py` `get_db_connection()`, `utils.py` | Connection pool, CRUD for call_logs, org_configs |
| `services/auth.py` | `ui_server.py` lines 54-61, 300-350 | JWT sign/verify, password hashing |
| `services/webhook.py` | `utils.py` HMAC delivery | HMAC-signed POST to MantraAssist backend |
| `services/s3.py` | `utils.py` S3 recording | S3 upload with optional graceful skip |
| `services/sip.py` | `ui_server.py` SIP trunk endpoints | Provider resolution, trunk provisioning, error classification |

**Deliverable:** `services/` is importable; all business logic callable without HTTP. `ui_server.py` is noticeably thinner.

### Phase 4: Routers Layer (Day 9-11)

Extract HTTP endpoints from `ui_server.py` into dedicated router files:

| Router | Extracts | Endpoints |
|--------|----------|-----------|
| `routers/webhooks.py` | ~300 lines | `POST /api/v1/call/inbound` |
| `routers/sip.py` | ~250 lines | `POST /.../twilio`, `/plivo`, `/zadarma`, SIP setup/inbound |
| `routers/auth.py` | ~80 lines | `POST /login` |
| `routers/dashboard.py` | ~200 lines | Metrics, active calls, SSE stream, call history |
| `routers/kb.py` | ~150 lines | Ingest, search, delete, chat |
| `routers/dispatch.py` | ~80 lines | `POST /dispatch-test` |
| `routers/health.py` | ~30 lines | `GET /health` |

**Deliverable:** `ui_server.py` becomes a thin `main.py` that just imports routers and calls `app.include_router()`. Original file can be deleted.

### Phase 5: Agent Subsystem (Day 12-16)

Split `agent.py` (1,617 lines) into the `agent/` package:

| File | Lines Extracted | Content |
|------|----------------|---------|
| `agent/entrypoint.py` | ~50 | `run_agent()` entrypoint, `entrypoint()` async fn |
| `agent/pipeline.py` | ~150 | STT/LLM/TTS/VAD/turn detector setup and wiring |
| `agent/session.py` | ~200 | Room connect, participant events, chat context, metadata handling |
| `agent/context.py` | ~80 | `resolve_inbound_context()`, KB scope resolution |
| `agent/handoff.py` | ~100 | `transfer_to_human` orchestration (SIP participant, silence, webhook) |
| `agent/finalize.py` | ~250 | `finalize()` — recording stop, analysis, webhook, DB save |
| `agent/safety.py` | ~150 | Inactivity monitor, farewell detection, call duration limiter |
| `agent/tools/__init__.py` | ~30 | Tool registration |
| `agent/tools/search_kb.py` | ~60 | `search_knowledge_base` |
| `agent/tools/handoff.py` | ~40 | `transfer_to_human` tool fn |
| `agent/tools/end_call.py` | ~40 | `end_call` tool fn |

**Deliverable:** `agent.py` deleted. Voice agent runs from `agent/entrypoint.py`. Each subsystem is independently testable.

### Phase 6: Dispatcher + Routines (Day 17-18)

- Move `dispatcher.py` into `dispatcher/worker.py` + `dispatcher/capacity.py`
- Create `routines/dispatcher_loop.py` and `routines/zombie_cleanup.py`
- Extract the 0.5s polling loop from main into `routines/`

**Deliverable:** Dispatcher is a proper background routine with clean separation of concerns.

### Phase 7: KB Engine (Day 19-20)

- Move `knowledge_base.py` into `kb/engine.py` + `kb/chunker.py`
- Move `retriever.py` into `kb/retriever.py`
- Create `kb/migration.py` for schema bootstrap

**Deliverable:** KB is a self-contained sub-package.

### Phase 8: Tests + Cleanup (Day 21-25)

- Write tests for each module (see `tests/` structure above)
- Remove all dead code paths (deprecated Plivo XML endpoints, commented-out code)
- Update `pyproject.toml` entrypoints to point to new locations
- Update `entrypoint.sh` and `Dockerfile` if paths changed
- Update `obsidian/` vault docs to reflect new structure

**Deliverable:** Green test suite, clean codebase, updated docs.

---

## 5. How to Add a New Feature After Restructure

### Example: Adding a new LLM tool "book_appointment"

**Step 1:** Create `app/agent/tools/appointment.py`
```python
from livekit.agents import llm

@llm.tool
async def book_appointment(
    context: llm.ToolContext,
    doctor_name: str,
    date_time: str,
) -> str:
    """Book an appointment with a doctor. Call this when the user wants to schedule.
    
    Args:
        doctor_name: The doctor's full name
        date_time: Preferred date and time in ISO format
    """
    # Business logic goes in the tool function
    return f"Appointment booked with {doctor_name} at {date_time}"
```

**Step 2:** Register in `app/agent/tools/__init__.py`
```python
from .appointment import book_appointment

AGENT_TOOLS: list[llm.Tool] = [
    search_kb,
    transfer_to_human,
    end_call,
    book_appointment,  # <-- added here
]

def get_agent_tools() -> list[llm.Tool]:
    return AGENT_TOOLS
```

**Step 3:** If the tool needs external data, add logic to a service:
- Appointment booking business → `app/services/appointment.py` (new file)
- Tool calls `appointment_service.book(...)`

**Step 4:** If the tool needs API endpoints:
- Thin router → `app/routers/appointments.py`
- POST endpoint calls `appointment_service.book(...)`
- Registered in `main.py` via `app.include_router()`

### Adding a new features step by step

```
                     ┌─────────────────────┐
                     │  New Feature Idea    │
                     └──────────┬──────────┘
                                │
                    ┌───────────┴───────────┐
                    │  Has HTTP endpoint?    │
                    └──────┬──────┬──────────┘
                          YES     NO
                          │       │
                 ┌────────┘       └────────┐
                 │                          │
        ┌────────┴────────┐      ┌─────────┴─────────┐
        │ routers/feature  │      │ agent/tool_name.py │
        │ .py (thin)       │      │ + __init__.py reg  │
        └────────┬────────┘      └─────────┬──────────┘
                 │                          │
                 └──────────┬───────────────┘
                            │
                 ┌──────────┴──────────┐
                 │ services/feature.py  │
                 │ (business logic)     │
                 └──────────┬──────────┘
                            │
                 ┌──────────┴──────────┐
                 │ models/feature.py    │
                 │ (Pydantic schemas)   │
                 └──────────────────────┘
```

---

## 6. File Size Budget (Hard Limits)

To prevent regression into monolith files:

| Directory | Max Lines Per File | Enforcement |
|-----------|-------------------|-------------|
| `routers/` | 150 | Peer review |
| `services/` | 300 | Peer review |
| `agent/*.py` | 200 | Peer review |
| `agent/tools/*.py` | 100 | Peer review |
| `kb/*.py` | 300 | Peer review |
| `models/*.py` | 150 | Peer review |
| `config/*.py` | 200 | Peer review |
| `routines/*.py` | 150 | Peer review |

If a file exceeds its budget, it must be split into a sub-package.

---

## 7. Dependency Flow

Strict import rules (enforced by convention, optionally by `deptrace` / `pytest-import-check`):

```
routers/  ──────>  services/  ──────>  models/
    │                    │
    │                    └──────────>  config/
    │                   
    └──────────────────────────────>  models/

agent/  ────────>  services/  ──────>  models/
    │                    │
    │                    └──────────>  config/
    │
    ├──>  stt/
    ├──>  llm/
    ├──>  tts/
    ├──>  kb/
    ├──>  recording/
    └──>  alerter/

routines/ ──────>  services/  ──────>  models/
                      │
                      └──────────>  config/

models/  ────────> (nothing — leaf node)
config/  ────────> (nothing — leaf node)
```

**Rules:**
- `routers/` may NOT import from `agent/` directly (use services as bridge)
- `agent/` may NOT import from `routers/` (reverse dependency)
- `services/` may NOT import from `routers/` or `agent/`
- `models/` must be a leaf — no imports from any `app/` module
- `config/` must be a leaf — no imports from any `app/` module
- Circular imports are forbidden

---

## 8. Tool Registration Pattern

### `agent/tools/__init__.py`
```python
"""Central tool registry — add new tools here to make them available."""

from .search_kb import search_knowledge_base
from .handoff import transfer_to_human
from .end_call import end_call
from .appointment import book_appointment  # example new tool

__all__ = [
    "search_knowledge_base",
    "transfer_to_human",
    "end_call",
    "book_appointment",
]

# Optional: categorize tools by domain for service filtering
TOOL_CATEGORIES: dict[str, list[str]] = {
    "kb": ["search_knowledge_base"],
    "handoff": ["transfer_to_human"],
    "call_control": ["end_call"],
    "appointment": ["book_appointment"],
}
```

### `agent/tools/__template.py`
```python
"""Template for creating a new LLM tool.
Copy this file, rename, and implement the function body."""

from livekit.agents import llm


@llm.tool
async def your_tool_name(
    context: llm.ToolContext,
    # Add your parameters here
    param1: str,
    param2: int = 0,
) -> str:
    """Tool description — this is what the LLM sees.
    
    Write a clear description so the LLM knows when to call this tool.
    
    Args:
        param1: Description of param1
        param2: Description of param2 (default: 0)
    
    Returns:
        A string response for the LLM
    """
    # Your business logic here
    # Use services/ for external calls (DB, API, Redis)
    result = f"Processed {param1} with value {param2}"
    return result
```

---

## 9. Router Pattern

### `routers/__template.py`
```python
"""Template for creating a new API router."""

from fastapi import APIRouter, Depends
from app.models.feature import FeatureRequest, FeatureResponse
from app.services.feature import FeatureService

router = APIRouter(prefix="/api/v1/feature", tags=["feature"])


@router.post("/action")
async def feature_action(
    body: FeatureRequest,
    service: FeatureService = Depends(get_feature_service),
):
    """Short description of what this endpoint does."""
    result = await service.do_something(body)
    return FeatureResponse(status="ok", data=result)
```

---

## 10. Service Pattern

### `services/__template.py`
```python
"""Template for creating a new service."""

from app.config.settings import settings
from app.models.feature import FeatureRequest


class FeatureService:
    """Business logic for the feature domain.
    
    This class has NO HTTP awareness. It receives typed models and returns
    typed models. It can be used by routers, agent tools, and other services.
    """
    
    def __init__(self, db_pool=None, redis_client=None):
        self.db = db_pool
        self.redis = redis_client
    
    async def do_something(self, request: FeatureRequest) -> dict:
        # Business logic here
        return {"result": "success"}
```

---

## 11. Migration Sequence (File-by-File)

| Step | Action | Files Changed / Created |
|------|--------|------------------------|
| 1 | Scaffold `app/` package | `app/__init__.py`, all sub-package `__init__.py` files |
| 2 | Extract config | `app/config/settings.py`, `app/config/constants.py`, `app/config/logging.py` |
| 3 | Extract prompts | `prompts/system.md`, `prompts/handoff.md`, `prompts/farewell.md`, `prompts/analysis.md`, `prompts/guardrails.md` |
| 4 | Create Pydantic models | `app/models/*.py` (6 files) |
| 5 | Extract services | `app/services/*.py` (7 files) |
| 6 | Extract routers | `app/routers/*.py` (7 files) |
| 7 | Rewrite `main.py` | `app/main.py` (replaces 80% of `ui_server.py`) |
| 8 | Delete `ui_server.py` | — |
| 9 | Split `agent.py` → `agent/` | `app/agent/*.py` (8 files) + `app/agent/tools/*.py` (4 files) |
| 10 | Delete `agent.py` | — |
| 11 | Split `dispatcher.py` → `dispatcher/` | `app/dispatcher/*.py` (2 files) + `app/routines/*.py` (2 files) |
| 12 | Delete `dispatcher.py` | — |
| 13 | Split `knowledge_base.py` → `kb/` | `app/kb/*.py` (4 files) |
| 14 | Delete `knowledge_base.py` | — |
| 15 | Split `email_alerts.py` → `alerter/` | `app/alerter/email.py` |
| 16 | Delete `email_alerts.py` | — |
| 17 | Move `retriever.py` → `kb/` | `app/kb/retriever.py` |
| 18 | Delete `retriever.py` | — |
| 19 | Move `utils.py` → services | Dissolve into `app/services/s3.py`, `app/services/webhook.py`, `app/services/db.py` |
| 20 | Delete `utils.py` | — |
| 21 | Move `static/` → `app/static/` | — |
| 22 | Create `tests/` scaffold | `tests/conftest.py`, test files |
| 23 | Update `pyproject.toml` | Entrypoints, package discovery |
| 24 | Update `entrypoint.sh` / `Dockerfile` | Path references |
| 25 | Delete old `mantra/` package | — |

---

## 12. Success Criteria

The restructure is complete when:

1. **No file exceeds its size budget** (see §6)
2. **No circular imports** exist in the `app/` package
3. **`main.py` is <150 lines** (just imports + router registration + lifespan)
4. **Every env var is typed** in `config/settings.py`
5. **Every data shape has a Pydantic model** in `models/`
6. **Every prompt string is in a `.md` file** in `prompts/`
7. **All business logic is in `services/` or `agent/`** — routers are purely HTTP glue
8. **`ui_server.py`, `agent.py`, `utils.py`, `dispatcher.py`, `knowledge_base.py`, `retriever.py`, `email_alerts.py`** no longer exist
9. **Test coverage exists** for at least the critical paths: webhook dispatch, SIP call placement, handoff, post-call finalization, KB search
