# Architecture Overview

## Pattern

Modular, asynchronous, multi-process architecture based on Python `asyncio`.

## Processes

| Process | File | Role |
|---------|------|------|
| Agent Worker | `mantra/agent.py` (~1,629 lines) | Connects to LiveKit rooms, handles real-time STT→LLM→TTS voice pipeline + TOS telemetry |
| Dispatcher | `mantra/dispatcher.py` (~223 lines) | Background loop: pops Redis queue → checks capacity → dispatches to LiveKit + TOS telemetry |
| UI/API Server | `mantra/ui_server.py` (~3,613 lines) | FastAPI HTTP server: webhooks, SIP trunk management, per-provider capacity gating, health gate, dashboard APIs, KB ingestion, org config CRUD |
| MCP Server | `mcp/server.py` (~1,073 lines) | Model Context Protocol server exposing PostgreSQL tools (patients, doctors, hospitals, appointments, call logs, DB schema) |

## System Diagram

```
┌─────────────┐     HTTP POST     ┌───────────────┐   Redis Queue    ┌──────────────┐
│   External   │ ─── webhook ──>  │  UI/API Server │ ── queue:pending ─>  Dispatcher  │
│  Telephony   │                  │  (FastAPI)     │                  │  (background)│
│  (Twilio/    │ <── SIP call ──  │  :8081         │                  └──────┬───────┘
│   Plivo/     │                  └───────┬───────┘                         │
│   Zadarma/   │                          │                                 │
│   VoiceLink) │                          │                                 │
└─────────────┘                            │                          ┌──────┴──────┐
                                    ┌───────┴───────┐                  │ LiveKit     │
                                    │  Static Files  │                  │ Cloud API   │
                                    │  (HTML/JS/CSS) │                  └──────┬──────┘
                                    └───────┬───────┘                         │
                                            │                          ┌──────┴──────┐
                                    ┌───────┴───────┐                  │ Voice Agent │
                                    │  PostgreSQL   │                  │ agent.py    │
                                    │  (call_logs   │                  │             │
                                    │   + kb_pages) │                  │ STT→LLM→TTS│
                                    └───────────────┘                  └──┬──────┬───┘
                                                                          │      │
                             ┌────────────────────┐               ┌──────┘      └──────┐
                             │  AWS S3 (recordings)│               │  Human Agent       │
                             └────────────────────┘               │  (SIP Participant  │
                                                                   │   dialed into room)│
                                                                   └────────────────────┘
```

## Key Architecture Decisions

1. **Redis as coordination layer** — Queue, active call state, capacity tracking all live in Redis
2. **Two LiveKit API clients** — Direct (Twilio/Zadarma) + Proxied (Plivo for India routing)
3. **In-memory session recording** — `SessionRecorder` holds audio as numpy arrays, never touches disk
4. **HMAC-signed webhooks** — Post-call data sent to MantraAssist backend with SHA-256 signing
5. **Fallback TTS** — Migrated from Cartesia to LiveKit native `sonic-3` TTS (no external API dependency for TTS)
6. **Handoff via co-room SIP** — Human agent dialed into the same LiveKit room as AI + caller, then AI silenced via `update_instructions` (currently disabled, code preserved)

See [[Architecture/Design Decisions.md]] for the full decision log.
