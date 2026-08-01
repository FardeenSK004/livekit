# Master Agent

## When to Use This Vault

Start here whenever resuming work on this repository. Read [[Home.md]] → [[Architecture/Overview.md]] → [[Development/Current Sprint.md]].

## Repository Summary

Production-grade bilingual voice AI agent built on LiveKit Cloud for inbound + outbound telephony. Orchestrates STT→LLM→TTS pipeline with per-provider capacity gating, SIP trunking (Twilio/Plivo/Zadarma/VoiceLink), PostgreSQL FTS knowledge base, and post-call processing (S3 + PostgreSQL + CRM webhook + TOS telemetry).

## Key Files

| File | Role |
|------|------|
| `mantra/agent.py` | Voice agent worker (1,629 lines) |
| `mantra/ui_server.py` | HTTP API + dashboard server (3,613 lines) |
| `mantra/dispatcher.py` | Redis queue consumer (223 lines) |
| `mantra/utils.py` | Recording, analysis, webhooks, telemetry (595 lines) |
| `mantra/knowledge_base.py` | PostgreSQL FTS KB (561 lines) |
| `mantra/email_alerts.py` | Crash notifications (244 lines) |
| `mcp/server.py` | Postgres MCP server — 13 tools (1,073 lines) |
| `static/` | Frontend (HTML/JS/CSS) |

## Before Making Changes

1. Read [[Architecture/Overview.md]]
2. Read [[Development/TODO.md]]
3. Update [[Development/Changelog.md]] after
4. Update relevant feature docs
