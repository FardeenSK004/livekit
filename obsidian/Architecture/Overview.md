# Architecture Overview

## Pattern

Modular, asynchronous, multi-process architecture based on Python `asyncio`.

## Processes

| Process | File | Role |
|---------|------|------|
| Agent Worker | `mantra/agent.py` (~1,008 lines) | Connects to LiveKit rooms, handles real-time STT→LLM→TTS voice pipeline + TOS telemetry |
| Dispatcher | `mantra/dispatcher.py` (~190 lines) | Background loop: pops Redis queue → checks capacity → dispatches to LiveKit + TOS telemetry |
| UI/API Server | `mantra/ui_server.py` (~1,120 lines) | FastAPI HTTP server: webhooks, SIP trunk management, health gate, dashboard APIs |
| MCP Server | `mcp/server.py` (177 lines) | Model Context Protocol server exposing PostgreSQL tools |

## System Diagram

```
┌─────────────┐     HTTP POST     ┌───────────────┐   Redis Queue    ┌──────────────┐
│   External   │ ─── webhook ──>  │  UI/API Server │ ── queue:pending ─>  Dispatcher  │
│  Telephony   │                  │  (FastAPI)     │                  │  (background)│
│  (Twilio/    │ <── SIP call ──  │  :8081         │                  └──────┬───────┘
│   Plivo/     │                  └───────┬───────┘                         │
│   Zadarma)   │                          │                                 │
└─────────────┘                            │                          ┌──────┴──────┐
                                   ┌───────┴───────┐                  │ LiveKit     │
                                   │  Static Files  │                  │ Cloud API   │
                                   │  (HTML/JS/CSS) │                  └──────┬──────┘
                                   └───────┬───────┘                         │
                                           │                          ┌──────┴──────┐
                                   ┌───────┴───────┐                  │ Voice Agent │
                                   │  PostgreSQL   │                  │ agent.py    │
                                   │  (call_logs)  │                  │             │
                                   └───────────────┘                  │ STT→LLM→TTS│
                                                                      └─────────────┘
                            ┌────────────────────┐
                            │  AWS S3 (recordings)│
                            └────────────────────┘
```

## Key Architecture Decisions

1. **Redis as coordination layer** — Queue, active call state, capacity tracking all live in Redis
2. **Two LiveKit API clients** — Direct (Twilio/Zadarma) + Proxied (Plivo for India routing)
3. **In-memory session recording** — `SessionRecorder` holds audio as numpy arrays, never touches disk
4. **HMAC-signed webhooks** — Post-call data sent to MantraAssist backend with SHA-256 signing
5. **Fallback TTS** — Multiple Cartesia API keys cycled on rate limits via `FallbackAdapter`

See [[Architecture/Design Decisions.md]] for the full decision log.
