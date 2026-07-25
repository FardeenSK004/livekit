# Mantra Voice Agent — Knowledge Base

> **Version:** 0.1.0  
> **Package:** `livekit-agent` (`app/`)  
> **Repository:** `git@github.com:FardeenSK004/livekit.git` (fork of Mantracare-Org/livekit)  
> **Last Updated:** 2026-07-25

---

## Quick Links

| Area | Document |
|------|----------|
| 🏛️ Architecture | [[Architecture/Overview.md\|Overview]] · [[Architecture/Components.md\|Components]] · [[Architecture/Data Flow.md\|Data Flow]] |
| 🌐 APIs | [[Architecture/APIs.md\|API Reference]] |
| 🗄️ Database | [[Architecture/Database.md\|Database Schema]] |
| ⚙️ Infrastructure | [[Architecture/Infrastructure.md\|Infrastructure]] |
| 🔧 Restructure | [[Architecture/Restructure Plan.md\|Restructure Plan]] · [[Development/Restructure Implementation.md\|Implementation]] · [[Development/Restructure Verification Report.md\|Verification Report]] |
| 🎯 Features | [[Features/Feature Index.md\|Feature Index]] |
| 📋 Development | [[Development/TODO.md\|TODO]] · [[Development/Changelog.md\|Changelog]] · [[Development/Bugs.md\|Bugs]] · [[Development/Current Sprint.md\|Current Sprint]] |
| 🧠 Knowledge | [[Knowledge/Coding Standards.md\|Coding Standards]] · [[Knowledge/Conventions.md\|Conventions]] |
| 📖 Context | [[Context/Project Summary.md\|Project Summary]] · [[Context/Stack.md\|Stack]] · [[Context/Repository Map.md\|Repository Map]] |

---

## Project Identity

**Mantra Voice Agent** is a production-grade, low-latency bilingual (English/Hindi) voice AI agent for telephony. Built on [[Context/Stack.md#LiveKit\|LiveKit]], it orchestrates an STT → LLM → TTS pipeline for real-time voice conversations over SIP telephony trunks (Twilio, Plivo, Zadarma).

## Architecture Snapshot

```
Telephony Provider → Webhook → FastAPI → Redis Queue → Dispatcher → LiveKit Cloud → Voice Agent
                                                                                       │
                                                                                  STT → LLM → TTS
                                                                                       │
                                                                                  Post-Call: S3 + Webhook + DB
```

## Key Stats

| Metric | Value |
|--------|-------|
| Package | `app/` (production; restructure complete on `feature/restructure`) |
| Frontend files | `static/` (+ copy under `app/static/`) |
| MCP server | 1 (`mcp/server.py`) |
| Agent entrypoint | `app/agent/entrypoint.py` |
| API server | `app/main.py` + `app/routers/*` |
| KB module | `app/kb/` |

---

## Recent Changelog

- **2026-07-25:** Final restructure verification — **GO WITH CAVEATS** (39/39 endpoint smoke; see [[Development/Restructure Verification Report.md|Verification Report]] / `report.md`)
- **2026-07-25:** Restructure cutover complete — `mantra/` removed; production entrypoints point at `app.*`
- **2026-06-30:** Cartesia TTS migrated to LiveKit Inference, removed redundant API key management, added env var fallbacks for MAX_CONCURRENCY
- **2026-06:** Dynamic tone/style configurations for agent prompts, emotional tone optimization for Cartesia
- **2026-05:** `end_call` tool with graceful disconnect, automated crash email notifications, webhook-based call log storage

---

## Repository Status

- **Deployment:** LiveKit Cloud (`mantraassist-0ek43ife`)
- **Testing:** `uv run python -m pytest tests/ -v`
- **Docs:** Obsidian vault at `obsidian/`
- **Active branch work:** `feature/restructure` — Phases 0–8 complete; final verification done (GO WITH CAVEATS)
