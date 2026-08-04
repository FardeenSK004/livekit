# Current Sprint

> **Sprint:** N/A (no formal sprint process)  
> **Last Updated:** 2026-08-05  
> **Status:** Active maintenance, trunk-based per-trunk call capacity gating, zombie room cleanup, DB enrichment

## Recently Completed

- [x] **Standard-String Timestamps for `next_call_on` (2026-08-05):** Renamed `normalize_to_iso8601` → `normalize_datetime` in `mantra/utils.py`; `next_call_on` is now delivered to webhooks as a standard server-local time string with `Z` suffix (`YYYY-MM-DD HH:MM:SSZ`) instead of ISO-8601 (`YYYY-MM-DDTHH:MM:SS`). `analyze_call` LLM prompt updated to emit `next_call_on` / `appointment_date_time` in server-local time instead of hardcoded IST.

- [x] **Post-Call Webhook Delivery & Finalize Refactoring (2026-08-04):** Refactored `finalize()` in `mantra/agent.py` with `_finalized` single-execution guard to prevent double webhooks. Guarded `fnc_ctx` and `recorder` accesses against null/unbound errors. Bounded `SessionRecorder.analyze_call` to 15s timeout and `upload_to_s3` to 10s timeout in `agent.py`, plus 12s timeout on `stream.collect()` in `mantra/utils.py`. Reduced Redis claim lock TTL to 300s (5 mins). Created `scripts/reprocess_unsent_calls.py` to identify and re-deliver unsent connected calls to the backend without altering payload schemas.
- [x] **Inbound Call KB Analysis & Webhook Payload Fixes (2026-08-04):** Enhanced `get_process_stage_data_for_kb_ids` in `mantra/knowledge_base.py` to query both `kb_pages.page_meta` and `kb_collections` (`process_description`, `stage_description`). Fixed `SessionRecorder.analyze_call` in `mantra/utils.py` to return `process_id` and extract automatic process/stage ID fallbacks from `process_stage_data`. Inbound calls analyze history against KB `process_stage_data` and send derived `process_id` and `stage_id`/`new_stage_id` integers in `CALL_DATA_INBOUND_UPDATE` to n8n without format changes.
- [x] **Trunk-Based Call Capacity Gating (2026-08-03):** Replaced provider-based concurrency with per-trunk capacity. Room naming changed from `call_{provider}_{call_id}` to `call_{trunk_id}_{call_id}`. Each trunk gets independent limit: Plivo trunks=2, Zadarma=3, VoiceLink=5, Twilio=3 (derived from `PROVIDER_DEFAULT_CONCURRENCY`). `_resolve_trunk_limit(trunk_id)` maps trunk→provider→limit via in-memory cache + LiveKit API + Redis fallback. Health check reports `trunk_capacity_{trunk_id}` per trunk. Middleware gate uses `_trunk_at_capacity(trunk_id)`.
- [x] **Zombie Room Cleanup (2026-08-03):** `cleanup_zombie_rooms()` in `dispatcher.py` (runs every 60s) + one-shot startup cleanup in `ui_server.py` lifespan. Lists LiveKit rooms, deletes `call_*` rooms with `num_participants == 0`. Prevents stale rooms from inflating capacity counts.
- [x] **DB Migration — Call Metadata (2026-08-03):** Added `caller_number`, `called_number`, `trunk_id` columns to `call_logs`. `save_call_log_to_db()` updated with new params. Agent `finalize()` extracts from `call_payload` (`call_from`, `client_phone`, `call_from_id`). `_log_blocked_call()` also passes caller number.
- [x] **DB Migration — kb_collections Process/Stage Descriptions (2026-08-03):** Added `process_description`, `stage_description` columns to `kb_collections`. Ingest endpoint extracts first process's description/name and first stage's description from `process_stage_data` JSON. `get_or_create_collection()` upserts both columns. Migration file: `migrations/add_trunk_fields.sql`.
- [x] **Inbound webhook int coercion + language matching (2026-08-02):** `CALL_DATA_INBOUND_UPDATE` coerces `org_id` / `process_id` / `new_stage_id` string→int via `_as_int()` when present (missing stays `null`). Agent prompt matches caller language every turn; STT switched Deepgram Nova-3 `language=hi` → `language=multi`.
- [x] **Plivo Zentrunk Trunk Reuse & Retry Self-Healing (inbound/setup):** Plivo trunk now found by name (not just `primary_uri_uuid`) so new-number setup reuses the domain trunk instead of failing with "already exists". 409 gate verifies Plivo number is actually linked to the trunk; partially-configured numbers complete setup idempotently on retry. `org_configs` written only after provider forwarding succeeds.
- [x] **SIP Failure → 503 (408/486):** Webhook now awaits `trigger_sip()` and returns empty `503` (matching the capacity gate) when the SIP call fails — 408→No Answer, 486→Busy, other→Incomplete. Failure classification written to Redis `sip_error_status:{call_id}`, room deleted, dedup lock released for retry.
- [x] **Per-Provider Call Capacity & Health Gating:** `PROVIDER_MAX_CONCURRENCY` (plivo=2, zadarma=3, voice_link=5), global `MAX_CALL_CONCURRENCY`=5. Provider embedded in LiveKit room name (`call_{provider}_{call_id}`) for zero-Redis tracking. `/health` reports `false` when any provider or the global pool saturates. Middleware returns empty `503` per-provider (webhooks) and global (all dispatch paths); provider saturation never blocks another provider's traffic. Blocked calls logged to `call_logs` as `Busy` with `provider_at_concurrency_limit` reason.
- [x] **Voicelink SIP Integration & Call Routing Fixes:** Fixed `voicelink_client` NameError, added inbound SIP setup support for `voice_link`, implemented Redis-backed trunk provider caching with `voicelink_client` fallback, and routed outbound VoiceLink calls through the proxied client (preventing 408 SIP timeout errors).
- [x] **Outbound Call Walkthrough doc:** Created `Architecture/Outbound Call Walkthrough.md` — full end-to-end trace of a single outbound call with payload sample, code references, sequence diagram, failure modes, and design properties
- [x] **Multi-KB per Org — KB Collections:** Added `kb_collections` table (migration `003_kb_collections.py`) where each row = one document = one KB collection per org. Agent resolves all collections for an org plus legacy fallback. Ingestion endpoints create/find collections.
- [x] **Voicelink SIP Inbound Trunk Provisioning:** Added SIP inbound trunk provisioning endpoints to `ui_server.py` for Voicelink integration.
- [x] **Inbound KB Document Metadata Tracking:** `KnowledgeRetriever` tracks accessed page metadata; `AssistantFunctions` extracts unique `process_id` values; `CALL_DATA_INBOUND_UPDATE` webhook carries specific KB process IDs.
- [x] Inbound KB document tracking — `CALL_DATA_INBOUND_UPDATE` now carries `process_id` from the specific KB document the agent searched during the call (not org-level config)
- [x] TTS migration to LiveKit native `sonic-3` (removed Cartesia dependency & health check)
- [x] TOS telemetry refinement — fire-and-forget post-processing, explicit `called_on` timestamp mapping
- [x] Directional farewell detection & webhook events in agent logic
- [x] SIP inbound trunk security update — allow all IP addresses for SIP inbound trunks

## In Progress

- [ ] **BLOCKER:** Fix MCP server — `CstdioServerParameters` attribute missing in `livekit.agents.llm.mcp` (upstream API changed)
- [ ] **BLOCKER:** Ingest KB data for org 66 — `kb_pages` table has zero rows for this org
- [ ] Fix post-call webhook 404 — n8n endpoint missing on ngrok backend
- [ ] Fix handoff TTS glitch — silence instructions race with tool return producing `"..."` utterance
- [ ] Set `AWS_S3_BUCKET_NAME` or suppress recording errors
- [ ] Migrate remaining `mantra/agent.py` tool callbacks to separate module

## Inbound Call Review (2026-07-22)

Live Plivo call vetted end-to-end. **Inbound flow is solid.** Issues found are in periphery:

| Area                              | Verdict        | Issue                                        |
| --------------------------------- | -------------- | -------------------------------------------- |
| Inbound webhook (Plivo → FastAPI) | ✅             | Works                                        |
| Inbound context resolution (DB)   | ✅             | Resolved org 66 from phone number            |
| Agent deployment (LiveKit)        | ✅             | Room created, agent answered                 |
| STT / LLM / TTS pipeline          | ✅             | Full conversation cycled                     |
| KB search                         | ❌             | No data for org 66                           |
| Handoff (`transfer_to_human`)     | ✅ (w/ glitch) | SIP participant added, but `"..."` TTS error |
| Post-call webhook                 | ❌             | 404 to n8n                                   |
| Recordings                        | ❌             | S3 not configured                            |

## Previously Completed

- [x] **2026-07-23** — Fixed Plivo inbound call: migrated from Plivo Application XML → Plivo Zentrunk SIP trunking
  1.  `<User>` + trunk ID + `;transport=tcp` → `UNALLOCATED_NUMBER`
  2.  `<Sip>` + trunk ID + `;transport=tcp` → `Invalid Answer XML`
  3.  `<User>` + `+918031321203` + `;transport=tcp` → `End Of XML Instructions` (`+` confuses Plivo's `<User>` parser)
  4.  `<User>` + `918031321203` → Plivo executes Dial but LiveKit returns `UNALLOCATED_NUMBER` (Plivo Application approach fundamentally incompatible)
  5.  **Zentrunk migration**: `_update_plivo_sip_forwarding` now creates Zentrunk origination URI → inbound trunk → links number directly via Plivo API. Plivo sends SIP INVITE directly to LiveKit's SIP domain without XML intermediary. Deprecated `_build_plivo_xml`, `/api/v1/sip/plivo-xml`, `/api/v1/sip/plivo-dial-status`.
- [x] **2026-07-21** — Fixed inbound call webhook payload: now includes `direction` and `inbound_context` (org_id, kb_id, phone_number, provider) for backend correlation
- [x] **2026-07-21** — Fixed MCP `call_logs` tool: was dead code (no SQL), now properly upserts into call_logs table
- [x] **2026-07-21** — Fixed `test_inbound_call` and `create_dispatch_rule` phone_number normalization
- [x] **2026-07-17** — Fix Knowledge Base ingestion UTF8 encoding errors and add detailed logger in `ui_server.py`
- [x] **2026-07-17** — Fix environment variable overriding consistency (`override=True` for `.env.local`)
- [x] **2026-07-16** — KB integration audit: confirmed KB is available to inbound calls via `search_knowledge_base` function tool; documented gap between docs and actual FTS-only implementation
- [x] **2026-07-16** — Local inbound mappings fallback (`inbound_mappings.json`) to test KB + inbound call integration without the external MantraAssist backend. Set `LOCAL_INBOUND_MAPPINGS=1` to skip backend entirely.
- [x] Add color-coded logging for inbound SIP setup payloads in `ui_server.py` — 2026-07
- [x] Race condition fix v2: lock TTL 30→600s + duplicate room guard + agent Redis trust fix — 2026-07-24
- [x] Race condition fix v1: Redis dedup lock + null safety + logger fix — 2026-07-24
- [x] Cartesia TTS migration to LiveKit Inference — 2026-06
- [x] Dynamic tone/style configurations for agent prompts — 2026-06
- [x] `end_call` tool with graceful disconnect — 2026-05
- [x] Automated crash email notifications — 2026-05
- [x] Webhook-based call log storage — 2026-05

## Resolved (was blocked)

- ~~Plivo proxy routing stability (India infra) — awaiting provider feedback~~ → **Root cause found and fixed**: Not a proxy issue. Plivo XML used `<User>` instead of `<Sip>`, causing Plivo to do internal SIP user lookup instead of forwarding to external LiveKit SIP endpoint. `PLIVO_PROXY` is only for API calls, not SIP signaling — proxy was never involved.
