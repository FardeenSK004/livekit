# Changelog

## 2026-08-02

### Inbound webhook int coercion + language matching
- **fix:** `CALL_DATA_INBOUND_UPDATE` coerces `org_id` / `process_id` / `new_stage_id` string→int when present; missing stays `null`.
- **fix:** Language matching prompt + STT `language=multi` so agent does not stick in Hindi after one Hindi filler.

## 2026-08-01

### Inbound SIP Setup — Plivo Zentrunk Trunk Reuse & Retry Self-Healing
- **fix:** Plivo Zentrunk inbound trunk is now found by its deterministic name (`Inbound via LiveKit ({domain})`) as well as by `primary_uri_uuid` in `_update_plivo_sip_forwarding()`. Previously a trunk created for an earlier number was missed by the URI-only match, so setup for a new number tried to create a duplicate and Plivo rejected it with "A trunk with the same name ... already exists" — even though no trunk was created by this attempt.
- **feat:** `_plivo_list_all()` — paginated helper for Plivo list endpoints (URI + trunk), so lookups no longer miss objects past the default 20-item page.
- **feat:** When a reused Zentrunk trunk points to a stale URI, it is repointed (`primary_uri_uuid`) to the current LiveKit SIP domain.
- **fix:** Retries after a failed provider config no longer return a false `409 number_already_configured`. The 409 gate now verifies, for Plivo, that the number is genuinely linked to the domain's Zentrunk trunk (`_plivo_number_is_linked_to_zentrunk()`); if not, setup falls through and completes idempotently reusing the existing LiveKit trunk + dispatch rule.
- **fix:** `org_configs` is now written only after provider forwarding succeeds, so a DB row reflects an actually-configured number instead of a partially-failed setup.

### Per-Provider Call Capacity & Health Gating
- **feat:** Per-provider concurrency limits in `ui_server.py` — `PROVIDER_MAX_CONCURRENCY` (`plivo: 2`, `zadarma: 3`, `voice_link: 5`), env-overridable via `PLIVO_MAX_CONCURRENCY` / `ZADARMA_MAX_CONCURRENCY` / `VOICELINK_MAX_CONCURRENCY`.
- **feat:** `/health` now reports per-provider and global capacity — returns `{"healthy": false}` when any provider is at its limit or total live `call_*` rooms reach `MAX_CALL_CONCURRENCY` (5, `CARTESIA_MAX_CONCURRENCY` fallback). Health check keys: `provider_capacity_{provider}`, `capacity_max_concurrency`.
- **feat:** Middleware `health_gate_middleware` (POST dispatch paths only) — per-provider gate for `/api/v1/webhooks/telephony` returns empty `503` when the call's provider is saturated; global gate returns `503` when live rooms ≥ `MAX_CALL_CONCURRENCY`; dependency gate still blocks `503` on infra failure. Provider saturation never blocks another provider's traffic.
- **feat:** Provider embedded in LiveKit room name for zero-Redis tracking — `call_{provider}_{call_id}` (e.g. `call_plivo_t1`, `call_voice_link_v1`); unknown trunks → `call_unknown_{id}` (not counted, not blocked).
- **feat:** `_log_blocked_call()` → `save_call_log_to_db(status="Busy")` with structured JSON (provider, `blocked: true`, `reason: provider_at_concurrency_limit`, active/max, trunk, phone, timestamp) when the per-provider gate rejects a call.
- **refactor:** Split `_run_dependency_checks()` (infra only, used by the coarse gate) from `_run_health_checks()` (deps + capacity, used by `/health`); `BYPASS_HEALTH_CHECKS` honored in both.
- **refactor:** `_get_provider_from_trunk()` returns `str | None` — removed `DEFAULT_PROVIDER="zadarma"`; all providers resolved equally via address inference + `voicelink_client` fallback; only non-None results cached in Redis.
- **fix:** `_active_call_rooms()` now re-raises LiveKit errors (fail-closed) instead of silently returning `[]` — previously caused intermittent gate bypass (200 instead of 503); middleware converts exceptions to `503`, `/health` records `capacity_max_concurrency: "error: ..."`.
- **fix:** Plivo SIP failure statuses now surface as `503` from the webhook — `handle_outbound_call_webhook` awaits `trigger_sip()` instead of fire-and-forget, and returns an empty `503` (matching the capacity gate) when the SIP call fails (408→`No Answer`, 486→`Busy`, other→`Incomplete`). Previously the webhook returned `200` even when the call never connected. The SIP failure classification is still written to Redis `sip_error_status:{call_id}` and the room is deleted.
- **chore:** Production cleanup — removed test/demo tooling (`tools/test_provider_capacity.py`, `tools/seed_rooms.py`, `tools/demo_7_calls.sh`, `tools/live_capacity_smoke.sh`) and `docs/CAPACITY_SYSTEM.md`; restored `_check_postgres()` in dependency checks; removed stale blank lines / dead code.

## 2026-07-30

### Voicelink Integration & SIP Fixes
- **fix:** Resolved `NameError: name 'voicelink_client' is not defined` by adding module-level client/session declarations and lifespan initialization.
- **feat:** Added `voice_link` / `voicelink` inbound SIP setup support and `_update_voicelink_sip_forwarding()` handler.
- **feat:** Updated inbound SIP trunk name default fallback to `{provider} {number}`.
- **feat:** Added Redis-backed trunk-to-provider caching in `_get_provider_from_trunk()` with `voicelink_client` fallback lookup for existing trunks.
- **fix:** Added `voice_link` branch in outbound SIP client selection to route through `voicelink_client` (proxied), preventing 408 SIP timeout errors.
- **refactor:** Cleaned up `_get_provider_from_trunk()` logic for cleaner execution and error logging.

### Outbound Call Walkthrough
- **doc:** Created `Architecture/Outbound Call Walkthrough.md` — full end-to-end trace from webhook payload through post-call processing with payload samples, code references, sequence diagram, failure modes, and design properties table

## 2026-07-29

### Multi-KB per Org — KB Collections
- **feat:** Added `kb_collections` table — each row = one document = one KB collection for an org. `kb_pages.kb_id` now stores the collection UUID instead of `org_id`. New migration: `003_kb_collections.py`.
- **feat:** `_resolve_from_db()` in `agent.py` now queries `kb_collections` to get all collection UUIDs for the org, plus the `org_id` as fallback for legacy data. Agent searches across all collections.
- **feat:** `/api/v1/kb/ingest` endpoint now creates/finds a `kb_collection` by `(org_id, document_id)` and stores pages under the collection UUID. Old data with `kb_pages.kb_id = org_id` still works via fallback.
- **feat:** New API endpoints: `GET /api/v1/kb-collections?org_id=X`, `GET /api/v1/kb-collections/{id}`, `DELETE /api/v1/kb-collections/{id}` for collection management.
- **feat:** `PostgresKnowledgeBase` gains 4 new methods: `get_or_create_collection`, `list_collections`, `delete_collection`, `get_kb_ids_for_org`.
- **refactor:** `delete_by_document` now removes pages by `document_id` across all KBs (not filtered by `kb_id`), and also cleans up the `kb_collections` row.
- **doc:** Updated `Database.md` with `kb_collections` table schema and KB resolution flow.

### Inbound KB Document Tracking
- **feat:** Added `accessed_pages_meta` tracking to `KnowledgeRetriever` — every `retrieve()` call now appends `page_meta` from returned pages, enabling per-document metadata extraction
- **feat:** Added `used_kb_process_ids` property to `AssistantFunctions` — reads tracked `page_meta` and returns unique `process_id` values from KB documents actually searched during the call
- **feat:** Inbound `finalize()` now overlays `process_id` from tracked KB pages into `call_payload` — the `CALL_DATA_INBOUND_UPDATE` webhook carries the `process_id` of the specific document the agent queried, not the org-level `org_configs.process_id`
- Files: `mantra/retriever.py` (lines 11, 44-46), `mantra/agent.py` (lines 298-314, 1248-1256)

## 2026-07-27

### TTS Fix & Payload Cleanup
- **fix:** TTS model changed from `cartesia/sonic-3` to `sonic-3` (LiveKit native inference, no Cartesia dependency)
- **fix:** Removed `emotion` extra_kwarg from TTS config (not supported by LiveKit inference)
- **fix:** Removed Cartesia API health check (TTS now uses LiveKit inference only)
- **fix:** Reverted TOS `Post-call processing complete` telemetry back to fire-and-forget (`create_bg_task`) — synchronous wait caused unnecessary blocking
- **feat:** Added `called_on` field to both n8n webhook payload and TOS telemetry data (maps from `call_initiated_at`)
- **chore:** Added payload body logging in `send_to_backend()` for easier debugging

## 2026-07-26

### Post-Call Data & Timestamps
- **fix:** `normalize_to_iso8601` outputs `YYYY-MM-DDTHH:mm:ss` (local, no offset) for `next_call_on` — matches MA reschedule format requirement
- **fix:** Post-call TOS telemetry (`[Agent Worker] Post-call processing complete`) now awaited directly instead of fire-and-forget bg task — ensures delivery of summary, transcript flag, stage, and timestamps to TOS
- **feat:** Added `call_initiated_at` (set by UI server on webhook receipt), `agent_joined_at`, `human_joined_at` as explicit fields in n8n webhook payload and TOS telemetry
- **feat:** `_telemetry()` helper in `entrypoint()` accepts `wait=True` for critical telemetry that must not be lost

### TOS Telemetry Cleanup
- **feat:** `report_telemetry()` now accepts optional `data` dict for structured payloads
- **feat:** Post-call processing sends rich TOS payload with `s3_recording`, `has_transcript`, `summary`, `new_stage_id`, `call_status`, `duration_seconds`, `backend_delivered`, `next_call_on`, appointment fields
- **refactor:** Stripped verbose debug logging from `report_telemetry()` (no more request body/headers printed)
- **refactor:** Stage telemetry messages use natural language (`"Call ended by agent"`, `"Customer joined the call"`, `"Agent voice engine ready"`)
- **chore:** Removed `log_io.py` colorama logging + `colorama` dependency (clean for production)

### Timezone Fix
- **fix:** `next_call_on` (scheduled call time) now sent in UTC in both `agent.py` and `utils.py` fallbacks
- **fix:** `email_alerts.py` crash timestamp uses local time (was labelled `UTC` but showed local)

## Earlier 2026-07-26

### TOS Telemetry & Health Gate

- **feat:** Added `report_telemetry()` to `mantra/utils.py` — POSTs structured telemetry logs to TOS endpoint (`/api/telemetry/{task_id}/log`). Used across all three services.
  - `AssistantFunctions.__init__` now parses `tos_task_id` from `job_metadata` and provides `_telemetry()` helper for tool callbacks.
  - Agent `entrypoint()` now reports: `agent_started`, `room_connected`, `participant_joined`, `voice_engine_initialized`, `post_processing_started`, `data_sent_to_backend`, `call_complete`.
  - Dispatcher reports: `call_dequeued`, `call_dispatched`, `dispatch_failed`.
  - UI server reports: `webhook_received`, `agent_dispatched`, `sip_call_initiating`, `sip_call_connected`, `sip_call_failed`.
- **feat:** Added `health_gate_middleware` to `ui_server.py` — blocks dispatch requests (`POST /dispatch-test`, `/api/v1/webhooks/telephony`, SIP trunk endpoints) with HTTP 503 if any critical service is down.
- **feat:** Comprehensive startup healthcheck — runs parallel checks on LiveKit, Redis, Deepgram, TTS (LiveKit native sonic-3), MantraAssist backend, PostgreSQL, S3 on server start.
- **feat:** Redis deduplication lock (`lock:call:{call_id}`, TTL 600s) on `handle_outbound_call_webhook` and `create_and_call_plivo` to prevent concurrent duplicate webhooks.
- **feat:** Room participant check in SIP failure handler — before cleanup, verifies SIP participant isn't already in room (duplicate guard from race condition fix v2).
- **fix:** `send_to_backend` URL corrected from `/webhooks/n8n` to `/api/v1/webhooks/n8n`.
- **refactor:** Removed Redis concurrency management (`calls:active`, `calls:status`) from `agent.py` — call tracking responsibility shifted to dispatcher + telemetry.
- **refactor:** Added persistent `httpx.AsyncClient` to UI server lifespan for all health checks.
- **refactor:** `get_db_connection` now prefers `DATABASE_URL` env var over individual PG env vars.
- **chore:** Logger handler guard in `ui_server.py` — prevents duplicate handler attachment.
- **chore:** `logger.propagate` set to `True` in `ui_server.py` for consistent log visibility.

## 2026-07-25

- **feat:** Comprehensive `/health` readiness endpoint — returns `healthy` / `stay` only when ALL services pass
  - Checks: LiveKit API, Redis, PostgreSQL, Deepgram STT, TTS (LiveKit native sonic-3), n8n backend, TOS endpoint, S3 bucket
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

## 2026-07-24

- **fix:** Raised concurrency limits — `AgentServer(num_idle_processes)` 1→20, `livekit.toml` replicas 1→2, `MAX_CONCURRENCY`/`LIVEKIT_MAX_ROOMS`/`AGENT_MAX_WORKERS` 5→20 across `.env`, `.env.local`. Root cause: agent deployment was pinned to 1 replica with 1 idle worker, capping effective concurrency at ~1-2 calls regardless of service-side limits.
- **doc:** Updated Environment.md capacity section

## 2026-07-23

- **fix:** Plivo inbound call — migrated from Plivo Application XML to Plivo Zentrunk SIP trunking. `_update_plivo_sip_forwarding` now creates Zentrunk origination URI → inbound trunk → links number via Plivo API. Deprecated `_build_plivo_xml`, `/api/v1/sip/plivo-xml`, `/api/v1/sip/plivo-dial-status`. Root cause: Plivo `<User>` Dial sends SIP INVITE that LiveKit rejects (UNALLOCATED_NUMBER); Zentrunk sends authenticated INVITE directly to LiveKit's SIP domain, matching the inbound trunk's numbers array.
- **doc:** Updated Obsidian vault: Current Sprint, Changelog

## 2026-07-22

- **analysis:** Inbound call + KB prod-readiness review on live Plivo call (org 66)
- **bug:** MCP server fails at startup — `module 'livekit.agents.llm.mcp' has no attribute 'CstdioServerParameters'` — DB tool unavailable to agent
- **bug:** KB retriever returned zero results for org 66 across 5 queries — likely empty `kb_pages` table, not a code issue
- **bug:** Post-call webhook to n8n returns 404 — ngrok endpoint lacks `/webhooks/n8n` route
- **bug:** Handoff TTS glitch — residual `"..."` utterance causes `APIError` traceback after `transfer_to_human` (race between tool return and silence instructions)
- **ops:** `AWS_S3_BUCKET_NAME` not set — recordings skipped
- **doc:** Confirmed `transfer_to_human` is fully implemented (not commented out as TODO claimed)
- **doc:** Updated Obsidian vault: Current Sprint, TODO, Components, Voice Agent, Architecture Overview

## 2026-07-21

- **fix:** Inbound call webhook payload now includes `direction`, `inbound_context` (org_id, kb_id, phone_number, provider) so MantraAssist backend can correlate inbound call results
- **fix:** Resolved inbound context (org_id, kb_id, etc.) now flows through to `finalize()` via `_effective_call_metadata` closure variable instead of being lost during metadata re-parse
- **fix:** MCP `call_logs` tool was broken (no SQL executed) — rewritten to properly upsert into `call_logs`
- **fix:** `test_inbound_call` and `create_dispatch_rule` endpoints now normalize `phone` → `phone_number` so agent can resolve inbound context
- **safety:** All new code paths wrapped in try/except with `non-fatal` logging; direction defaults to `"outbound"` so outbound system is completely unaffected
- **logging:** Added structured logging for webhook payload construction (direction, call_status, call_id) and inbound context addition

## 2026-07-18

- **feat:** DB Inbound Context Resolution: Added `org_configs` table and integration in `/api/v1/sip/inbound/setup` to map incoming phone numbers to organizations in the database. The agent now queries this DB first for context (prompt, voice, KB scope), supplementing the MantraAssist API. Added `/api/v1/org-configs` CRUD endpoints for backend management.
- **feat:** Add color-coded logging for inbound SIP setup requests/responses in `mantra/ui_server.py`
- **fix:** Knowledge Ingestion Encoding: Stripped null bytes (`\x00`) recursively from metadata and text inputs in `PostgresKnowledgeBase.add_page` and `delete_by_document` to prevent `CharacterNotInRepertoireError` (invalid byte sequence for UTF8).
- **feat:** Ingestion Logger: Added request parameters logging at the start of `/api/v1/kb/ingest` in `mantra/ui_server.py`.
- **refactor:** Env Loading: Updated `ui_server.py`, `dispatcher.py`, and migrations to load `.env` first and override with `.env.local` using `override=True` to resolve environment conflicts (e.g., Redis host/port).

## 2026-07-16

- **feat:** Added local inbound mappings fallback — `inbound_mappings.json` for testing KB + inbound call integration without the external MantraAssist backend
  - `resolve_inbound_context()` now falls back to local JSON config when the backend is unreachable
  - Set `LOCAL_INBOUND_MAPPINGS=1` env var to skip backend entirely and use local mappings only
- **doc:** Synced Obsidian vault with actual codebase state after KB audit
  - `Features/Knowledge Base.md` — Corrected from "pgvector + upfront prompt injection" to "PostgreSQL FTS + function tool RAG"; added known gaps, tag filtering docs, and accurate schema
  - `Architecture/Components.md` — Fixed line counts (agent.py: 1513, ui_server.py: 2143), added KB module section
  - `Architecture/Data Flow.md` — Added KB context resolution steps to inbound call flow
  - `Context/Repository Map.md` — Fixed line counts, added `knowledge_base.py` and `retriever.py`
  - `Context/Stack.md` — Updated PostgreSQL description to include KB FTS
  - `Home.md` — Fixed stats (7 modules, 6,206 total lines)

## 2026-07-03

- **feat:** Knowledge Base: Implemented absolute override 5-rule framework to force agent to answer factual questions directly (overriding strict prompt constraints like "never give advice")
- **refactor:** Knowledge Base: Made all prompt rules completely generic and industry-agnostic, removing hardcoded references to specific verticals like OCD/ERP

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