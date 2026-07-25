# Architecture Overview

## Pattern

Modular, asynchronous, multi-process architecture based on Python `asyncio`.

> **Restructure (2026-07-25):** Production runs from the `app/` package. The legacy `mantra/` monolith was removed after Phase 8 cutover. See [[Architecture/Restructure Plan.md]] and [[Development/Restructure Implementation.md]].

## Processes

| Process | Entry | Role |
|---------|-------|------|
| Agent Worker | `app.agent.entrypoint` | Connects to LiveKit rooms, handles real-time STT→LLM→TTS voice pipeline |
| Dispatcher | `python -m app.routines` | Background loop: pops Redis queue → checks capacity → dispatches to LiveKit |
| UI/API Server | `app.main` | FastAPI HTTP server: webhooks, SIP trunk management, static files, dashboard APIs |
| MCP Server | `mcp/server.py` | Model Context Protocol server exposing PostgreSQL tools |

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
                                    │  PostgreSQL   │                  │ app/agent   │
                                    │  (call_logs   │                  │ STT→LLM→TTS│
                                    │   + kb_pages) │                  └──┬──────┬───┘
                                    └───────────────┘                     │      │
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
4. **HMAC-signed webhooks** — Post-call data sent to MantraAssist backend with SHA-256 signing (`{body}.{timestamp}`)
5. **Handoff via co-room SIP** — Human agent dialed into the same LiveKit room as AI + caller, then AI silenced via `update_instructions`
6. **Layered `app/` package** — routers → services → models/config; agent/KB/dispatcher are self-contained subpackages

See [[Architecture/Design Decisions.md]] for the full decision log.
