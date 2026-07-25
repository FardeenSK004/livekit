# Changelog

## 2026-07-26

- **feat:** Added `health_gate_middleware` to block call dispatching if any critical service (LiveKit, Redis, etc.) is down.
- **fix:** Integrated post-call data pipeline (`TELEPHONY_UI_URL`) to ensure agent call logs are correctly saved to the local database via the UI server.

## 2026-07-25

- **feat:** Comprehensive `/health` readiness endpoint — returns `healthy` / `stay` only when ALL services pass
  - Checks: LiveKit API, Redis, PostgreSQL, Deepgram STT, Cartesia TTS, n8n backend, TOS endpoint, S3 bucket
  - Runs all checks in parallel with individual timeouts
  - Returns HTTP 200 + `"status": "healthy"` when every service is reachable
  - Returns HTTP 503 + `"status": "stay"` with per-service error breakdown otherwise
  - Files: `mantra/ui_server.py`

## 2026-07-24

- **fix:** Three-layer race condition hardening for outbound call webhooks
  - Increased Redis dedup lock TTL 30s → 600s to prevent late duplicates from passing through
  - Added room participant check in `trigger_sip` exception handler — skips cleanup if SIP participant already in room (duplicate guard)
  - Fixed agent `call_status` logic: only trust Redis SIP error if `user_joined` is False — prevents stale duplicate error from overriding real "Completed" status
  - Files: `mantra/ui_server.py` (lock TTL, room check), `mantra/agent.py` (Redis trust gate)

## 2026-06-30

- **doc:** Created `obsidian/` — comprehensive Obsidian knowledge base (48 files)
  - `Architecture/` — 8 files (overview, components, data flow, APIs, DB, infra, decisions, deps)
  - `Features/` — 10 files (index + 9 feature pages covering all modules)
  - `Development/` — 7 files (sprint, TODO, backlog, bugs, changelog, releases, roadmap)
  - `Agents/` — 6 files (master, backend, frontend, devops, docs, QA agent guides)
  - `Knowledge/` — 7 files (standards, conventions, best practices, commands, debugging, env, glossary)
  - `Context/` — 5 files (project summary, stack, repo map, external services)
  - `Templates/` — 3 file templates
  - `Inbox/` — placeholder
- **doc:** Updated root `README.md` to reference the Obsidian vault

## 2026-06-15

- **refactor:** Renamed `CARTESIA_MAX_CONCURRENCY` to `MAX_CONCURRENCY` + env var fallback
- **refactor:** Migrated Cartesia TTS to LiveKit Inference, removed redundant API key management
- **feat:** Webhook-based call log storage, updated DB query schemas
- **feat:** Dynamic tone and style configurations for agent prompts

## 2026-05

- **feat:** Emotional tone optimization for Cartesia voice synthesis
- **feat:** `end_call` tool with graceful disconnect + safety net
- **feat:** Automated crash email notifications
- **feat:** Gemini LLM integration
- **feat:** DeepSeek LLM integration
- **feat:** Plivo India proxy routing
- **feat:** Redis queue-based dispatcher system
- **feat:** Dashboard with SSE real-time metrics
- **feat:** JWT authentication
- **refactor:** Bilingual STT (Deepgram Hindi model)
- **refactor:** Custom ColorFormatter for multi-process logging
