# Backend Agent

## Context

Backend consists of `mantra/` Python package with FastAPI server, LiveKit agent, and utilities. TTS is LiveKit native `sonic-3` (no Cartesia dependency).

## Key Conventions

- All async, `asyncio` throughout
- Logging: `logger = logging.getLogger("mantra.{module}")`
- Env vars from `.env.local` with `dotenv`
- `try/except Exception as e: logger.error(...)` pattern for network boundaries

## Key Patterns

- Agent tools: `end_call` (active), `search_knowledge_base` (active), `transfer_to_human` (disabled)
- Per-provider capacity gating in middleware (Plivo=2, Zadarma=3, VoiceLink=5, Twilio=2, Global=5)
- Provider embedded in room name: `call_{provider}_{call_id}`
- Three LiveKit API clients: direct, plivo (proxied), voicelink (proxied)
- KB scope: multi-collection per org via `kb_collections` table + legacy org_id fallback
- Inbound context: DB-first resolution via `org_configs` table

## Testing

No automated tests exist. Manual testing via:
- `./dev.sh` to launch services
- `curl` to webhook endpoints
- Dashboard for metrics verification
