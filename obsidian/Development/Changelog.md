# Changelog

## 2026-08-10

### Inbound Call Post-Call `user_intent` Payload Field (Booked, Cancelled, Rescheduled)
- **feat:** Extended `user_intent` field in post-call `CALL_DATA_INBOUND_UPDATE` webhook payload for inbound calls to support 3 distinct appointment outcomes: `"APPOINTMENT_BOOKED"`, `"APPOINTMENT_CANCELLED"`, and `"APPOINTMENT_RESCHEDULED"`.
- **feat:** LLM call analysis in `SessionRecorder.analyze_call()` (`mantra/utils.py`) evaluates conversation history against KB process/stage descriptions:
  - `"APPOINTMENT_BOOKED"` iff an appointment was successfully booked during the call AND the outcome stage corresponds to appointment booking/confirmation.
  - `"APPOINTMENT_CANCELLED"` iff an existing appointment was cancelled during the call AND the outcome stage corresponds to appointment cancellation.
  - `"APPOINTMENT_RESCHEDULED"` iff an existing appointment was rescheduled to a new date/time during the call AND the outcome stage corresponds to appointment rescheduling.
  - `null` in all other cases (e.g. general inquiry, no appointment action).
- **feat:** Updated `finalize()` in `mantra/agent.py` to allow `"APPOINTMENT_BOOKED"`, `"APPOINTMENT_CANCELLED"`, or `"APPOINTMENT_RESCHEDULED"` in `CALL_DATA_INBOUND_UPDATE` payload sent to MantraAssist backend.
- **fix:** Inbound Greeting & Name Assumption:
  - Removed hardcoded `Identify yourself: 'Mantra Care'` instruction in `mantra/agent.py` which caused agents on inbound calls to greet with "Hi this is Mantra Care". Instructed agent to strictly follow custom prompt brand identity (e.g. `MantraAssist` or `Arushi`).
  - Stopped injecting stored DB `client_name` (e.g., `'Anurag'` from `org_configs`) into `ADDITIONAL CALL CONTEXT` on inbound calls so the agent never assumes an incoming caller's identity before they introduce themselves.
  - Added Turn-by-Turn Inbound Flow: Turn 1 (Greeting & "How can I help?"), Turn 2 (Caller states intent → Agent acknowledges and asks for caller's name before proceeding), Turn 3+ (Agent addresses request using caller's name naturally).
- **feat:** Post-Call Stage & Status Logic for No Transition:
  - When no stage transition occurs during a call (i.e. `new_stage_id` remains the same as initial `stage_id` or no useful outcome was achieved), `mantra/agent.py` now sends `new_stage_id: null` (empty data) instead of repeating `stage_id`.
  - Sets `call_status` to `"Incomplete"` in the webhook payload (`CALL_DATA_UPDATE` & `CALL_DATA_INBOUND_UPDATE`) when no new stage transition was made.
- **feat:** E.164 Inbound Phone Formatting:
  - Added `format_e164_phone_number()` helper function in `mantra/utils.py`.
  - Updated `CALL_DATA_INBOUND_UPDATE` payload in `mantra/agent.py` to ensure `client_phone_number` is formatted with country code and a leading `+` (e.g. `+918360625862`).
- **fix:** AMD Initial Greeting Latency Optimization & Non-Blocking Async Execution:
  - Re-architected AMD in `mantra/agent.py` to run asynchronously in a background task (`_run_amd_background()`) instead of blocking main call startup.
  - Initial greeting (`session.generate_reply()`) is now requested **immediately** upon call connection (0.2s delay), reducing initial speech playout latency from 6.0 seconds down to ~1.2 seconds.
  - If AMD detects voicemail during playout, it calls `session.interrupt()` to cancel initial greeting and leaves the voicemail message cleanly.
- **fix:** Relative Callback `next_call_on` Calculation:
  - Enhanced Task 3 prompt in `SessionRecorder.analyze_call()` (`mantra/utils.py`) to instruct relative date/time calculations (e.g., "call back in 10 minutes", "in 1 hour", "tomorrow at 3 PM") relative to current server time.
  - Added automatic Python regex fallback in `analyze_call()` that detects relative callback requests (e.g. `call me back in 10 minutes`) from call summary/transcript and calculates `next_call_on = current_time + timedelta(...)` automatically if the LLM output is missing.
- Files: `mantra/agent.py`, `mantra/amd.py`, `mantra/utils.py`

## 2026-08-09

### KB Retrieval Fix — Hybrid FTS + Semantic (pgvector/Gemini) + Tiered Fallback
- **bug:** Fixed org 77 inbound call failing to find "diagnostic codes" despite the KB page containing "diagnostic code". Root cause: `kb_pages.text_search` used the `simple` config with `websearch_to_tsquery` AND semantics — `'diagnostic' & 'codes'` never matched the stored `code` (no stemming, no OR fallback). Verified in scratch DB: `diagnostic codes` → 0 rows, `code`/`diagnostic` → 1 row.
- **feat:** Migration `006_kb_english_vector.py` — rebuilds `text_search` with the `english` config (stemming), enables the `vector` extension, adds `embedding vector(1536)`, and creates an HNSW index (`embedding vector_cosine_ops`). 1536 dims because pgvector HNSW/IVFFlat caps at 2000 dimensions (Gemini `output_dimensionality=1536` verified working).
- **feat:** New `mantra/gemini_embeddings.py` — lazy `google.genai.Client` singleton, `embed_texts()` (batch 100, 3 retries, exp backoff), `embed_text()`, `embedding_enabled()`. Uses `gemini-embedding-2` @ 1536 dims. NOTE: batch embeddings must use `types.Content(parts=[...])` — plain strings returned only 1 embedding for 2 inputs.
- **feat:** `mantra/knowledge_base.py` now performs tiered search: Tier A strict FTS (`english`) blended with pgvector cosine via Reciprocal Rank Fusion (`_blend_results`), soft-tag retry, Tier B loose OR query, Tier C tag-only, Tier D `list_available()` document listing. New query builders: `build_loose_search_query`, `build_vector_search_query`, `build_tag_search_query`, `build_list_docs_query`. `add_page()`/`ingest_text()` embed chunks up front with graceful FTS-only fallback when embeddings unavailable. Abstract `list_available` added.
- **feat:** `mantra/retriever.py` rewritten — tiered `retrieve()` with session cache; when nothing matches, returns the list of available documents (with tags) instead of a bare "no results", so the LLM can ask a better follow-up or answer truthfully. `_format_no_results` builds the doc list.
- **feat:** New `tools/backfill_embeddings.py` — idempotent/resumable backfill of `embedding` for existing rows (`--kb-id`, `--batch-size`, `--limit`, `--dry-run`). URL-encodes the DB password in the DSN.
- **feat:** Backfill logic extracted into `PostgresKnowledgeBase.backfill_embeddings()` and exposed two ways for Docker-only deployments: `POST /api/v1/kb/backfill-embeddings` HTTP endpoint (`mantra/ui_server.py`, body JSON `kb_id`/`batch_size`/`limit`/`dry_run`) and a `backfill` mode in `entrypoint.sh` (`docker run <image> backfill [args]`). Also added `mantra/migrations/006_kb_english_vector.sql` (transactional SQL variant of the migration). Both paths verified against scratch DB.
- **verified:** End-to-end scratch repro of the exact failure: org 77 page with `diagnostic code`, query "diagnostic codes" → page found; "diagnostics" → found (stemming); "what is there in your knowledge base" → truthful doc listing; "appointment booking" → doc listing (no hallucination). `get_kb_ids_for_org` / `get_collection_details_for_org` confirmed working. 1536-dim embedding stored + HNSW index validated.
- **unchanged:** `mantra/agent.py` — the `search_knowledge_base` tool already flows through `retriever.retrieve()`, so no code change needed there. Prod DB (52.7.20.203) untouched — migration SQL + backfill commands provided to the user to run.
- Files: `mantra/knowledge_base.py`, `mantra/retriever.py`, `mantra/ui_server.py`, `mantra/gemini_embeddings.py` (new), `mantra/migrations/006_kb_english_vector.py` (new), `mantra/migrations/006_kb_english_vector.sql` (new), `tools/backfill_embeddings.py` (new), `entrypoint.sh`

## 2026-08-07

### KB Process & Stage Persistence for Inbound Webhooks
- **feat:** Migration `005_kb_process_stage.py` — added `process_id`, `stage_id`, `stage_ids`, `process_assignments`, `process_description`, and `stage_description` columns to `kb_collections`, and `stage_id` to `org_configs`.
- **feat:** Updated `/api/v1/kb/ingest` in `mantra/ui_server.py` to parse Zod-schema aligned `process_assignments` (`[{"process_id": int, "stage_ids": [int]}]`) as well as explicit `process_id` and `stage_id` parameters, storing them directly on `kb_collections` and `kb_pages.page_meta`.
- **fix:** Updated `normalize_datetime()` in `mantra/utils.py` to output ISO-8601 UTC timestamp format (`YYYY-MM-DDTHH:MM:SSZ`, e.g. `"2026-08-04T10:59:36Z"`), returning `null` when no callback is scheduled for both inbound and outbound webhooks.
- **fix:** Updated `SessionRecorder.analyze_call()` in `mantra/utils.py` to evaluate `next_call_on` using a 3-tier priority: (1) User spoken callback time during the call, (2) Default stage callback delay instruction from `process_stage_data`/`stageDetails` in the call payload, (3) `null` if neither is present.
- **fix:** Updated 5-second silence prompt in `mantra/agent.py` to use natural Hindi phrasing (`"हेलो, क्या आप लाइन पर हैं?"`).
- Files: `mantra/utils.py`, `mantra/agent.py`

### AMD Exception Handling & Unevaluated LLM Compatibility
- **fix:** Updated `detect_voicemail()` in `mantra/amd.py` to handle early audio stream closures (`RuntimeError("amd closed before a result was available")`) as clean `info` logs rather than logging noisy multiline Python stack traces.
- **fix:** Added `suppress_compatibility_warning=True` to `AMD(...)` instantiation in `mantra/amd.py` for unevaluated LLMs like `deepseek-v4-flash`.
- Files: `mantra/amd.py`

## 2026-08-06

### Grafana Memory & CPU Arc Gauges
- **feat:** Added authentic Grafana Arc Gauge widgets for **Memory** and **CPU Utilization** to `static/network.html`.
- **feat:** Rendered 180° semi-circular arc gauge canvas with outer thin threshold ring (Green <70%, Orange 70-90%, Red >90%), inner progress arc fill, and centered dynamic value text (`114 MB`, `14.2%`).
- Files: `static/network.html`

### Call Retry Redis Deduplication Lock & DB Persistence
- **fix:** Resolved duplicate suppression bug where retrying a call within 5-10 minutes of a previous attempt logged `"delivered"` but skipped sending HTTP POST requests to the n8n backend.
- **fix:** Enhanced `_claim_backend_delivery` and `send_to_backend` in `mantra/utils.py` to deduplicate by `call_id + ai_call_id` (`f"backend_sent:{call_id}_{ai_call_id}"`).
- **fix:** Removed automatic `force=True` on `CALL_RETRY` inside `send_to_backend()`, eliminating double HTTP POST deliveries caused by the background Redis queue worker (`mantra:pending_webhooks`).
- **fix:** Updated `handle_outbound_call_webhook` in `mantra/ui_server.py` to automatically clear `backend_sent` and `lock:call:{call_id}` locks when a retry dispatch arrives.
- **feat:** Added automatic PostgreSQL persistence inside `send_to_backend()` in `mantra/utils.py` so every delivered webhook payload (including retries) is saved/upserted into `call_logs` and audited in `call_events`.
- Files: `mantra/utils.py`, `mantra/ui_server.py`

### Operations Dashboard DB Sync & Search
- **feat:** Updated `/api/v1/dashboard/calls` endpoint in `mantra/ui_server.py` to support `search` filtering (across call ID, caller/called phone numbers, and call log JSON text) and `status` filtering (`Completed`, `Busy`, `No Answer`, `Error`, `Incomplete`).
- **feat:** Updated `static/dashboard.html` and `static/dashboard.js` with search bar, status selector dropdown, manual "Sync DB" button, and auto-sync triggers on SSE call-end events and periodic 15s intervals.
- **feat:** Enhanced Call Details Inspect Modal in `static/dashboard.html` and `static/dashboard.js` to parse and render full AI summaries and turn-by-turn conversation transcripts (with styled 🤖 AI Agent and 👤 Caller speech bubbles, unicode Hindi/English support, and raw JSON fallback).

### Redis Operations & Queue Monitor
- **feat:** Created `/redis` route in `mantra/ui_server.py` serving `static/redis.html`.
- **feat:** Added Redis API endpoints: `/api/v1/redis/info` (server info, memory, clients, queue count, active count), `/api/v1/redis/queue` (inspect `queue:pending` sorted set items & payloads), `/api/v1/redis/active-details` (inspect `calls:active` hash, status, lock TTLs), `/api/v1/redis/keys` (scan and list keys by pattern with type and TTL), `/api/v1/redis/key-detail` (full value inspector), `/api/v1/redis/key` (delete key).
- **feat:** Created `static/redis.html` UI with summary metric cards, queue inspector table, active calls hash viewer, live key explorer, and JSON value inspector modal.

### Grafana-Style Network Telemetry Dashboard
- **feat:** Redesigned `static/network.html` with an authentic Grafana Dark Theme aesthetic (`#111217` canvas, `#181b1f` panels, Grafana orange/blue/green/red color palette).
- **feat:** Added top control toolbar with time range selector (`Last 5m`, `15m`, `30m`), refresh interval selector (`2s`, `5s`, `10s`, `Off`), and manual refresh.
- **feat:** Added single stat cards for Request Rate (RPS), Avg Response Latency (ms) + estimated p95, Error Rate %, RAM Memory usage, and CPU seconds.
- **feat:** Added time-series line charts for Throughput (RPS), Latency Distribution (Avg/p95), HTTP Status Code Breakdown over time (`2xx`, `3xx`, `4xx`, `5xx`), and Top API Endpoints volume bar chart.
- **feat:** Added high-density Grafana endpoint metrics grid table with status code class filtering (`2xx`, `3xx`, `4xx`, `5xx`), live search filtering, and human-readable API endpoint labels (mapping raw technical paths like `/api/v1/stream` → **Real-Time SSE Stream** and `/api/v1/redis/active-details` → **Redis Active Calls Inspector**).

### Redis Webhook Worker Failover & Read-Only Replica Reconnection Fix
- **fix:** Updated `process_pending_webhooks()` worker in `mantra/ui_server.py` to handle Redis failovers (Master → Replica transitions) and socket read timeouts.
- **fix:** Added exception handlers for `ReadOnlyError` ("You can't write against a read only replica") and `ResponseError` ("UNBLOCKED force unblock..."). When failover occurs, the worker logs a warning, closes/disconnects the stale Redis connection pool (`await client.aclose()`), resets `client = None`, and reconnects cleanly on the next iteration.
- **fix:** Configured `socket_timeout=15`, `socket_connect_timeout=5`, `health_check_interval=15`, and `retry_on_timeout=True` on `redis.from_url` to prevent socket hanging and ensure swift reconnects.
- Files: `mantra/ui_server.py`, `static/dashboard.html`, `static/dashboard.js`, `static/redis.html`, `static/network.html`, `static/index.html`, `static/kb_chat.html`

## 2026-08-05

### Standard-String Timestamps for `next_call_on`
- **fix:** Renamed `normalize_to_iso8601` → `normalize_datetime` in `mantra/utils.py`. It now returns `next_call_on` as a standard server-local time string (`YYYY-MM-DD HH:MM:SSZ`, `Z` suffix appended) instead of ISO-8601 (`YYYY-MM-DDTHH:MM:SS`).
- **fix:** `analyze_call` LLM prompt in `mantra/utils.py` no longer hardcodes IST — `next_call_on` / `appointment_date_time` are now instructed to be emitted in the server's local time (`YYYY-MM-DD HH:MM:SS`), matching the `datetime.now()`-based `current_time_str`.
- **fix:** Updated `mantra/agent.py` import and both `CALL_DATA_INBOUND_UPDATE` / `CALL_DATA_UPDATE` webhook payloads to use the renamed helper, so `next_call_on` is delivered as a plain string in server-local time.
- Files: `mantra/utils.py`, `mantra/agent.py`

## 2026-08-04

### Post-Call Webhook Delivery & Finalize Refactoring
- **fix:** Added `_finalized` single-execution guard in `finalize()` in `mantra/agent.py` to prevent duplicate post-call execution and double-webhook delivery.
- **fix:** Guarded all `fnc_ctx` and `recorder` accesses in `finalize()` against uninitialized/None states, preventing `AttributeError` / `UnboundLocalError` from terminating finalization early.
- **fix:** Added 15s timeout on `SessionRecorder.analyze_call` and 10s timeout on `upload_to_s3` in `mantra/agent.py` so slow LLM or S3 requests never block post-call backend delivery.
- **fix:** Added 12s timeout to `stream.collect()` in `mantra/utils.py` `analyze_call` method.
- **fix:** Reduced Redis claim TTL in `_claim_backend_delivery` from 3600s (1 hour) to 300s (5 minutes) so failed/interrupted claims don't lock `call_id` retries for an hour.
- **feat:** Created `scripts/reprocess_unsent_calls.py` to automatically scan PostgreSQL for connected calls that missed backend webhook delivery and re-deliver their payloads.
- Files: `mantra/agent.py`, `mantra/utils.py`, `scripts/reprocess_unsent_calls.py`

### Webhook Schema & Inbound Call KB Analysis
- **fix:** Enhanced `get_process_stage_data_for_kb_ids` in `mantra/knowledge_base.py` to query both `kb_pages` (`page_meta->process_stage_data`) and `kb_collections` fallback (`process_description`, `stage_description`), ensuring KB process/stage structures are always present for inbound call analysis.
- **fix:** Fixed missing `process_id` in `SessionRecorder.analyze_call` return dictionary in `mantra/utils.py` — previously `analyze_call` dropped `process_id`, causing `derived_process_id` to evaluate to `None` and downstream PDO prepared statement parameter errors.
- **fix:** Added automatic fallback extraction for `process_id` and `stage_id` from `process_stage_data` in `analyze_call` when LLM returns null or fails to parse.
- **fix:** Inbound calls perform full KB analysis using `SessionRecorder.analyze_call` on conversation history against `process_stage_data` (sourced from accessed KB pages or queried directly from `kb_pages` / `kb_collections` in DB by `kb_ids`).
- **fix:** The derived `process_id` and `stage_id` / `new_stage_id` are populated in the standard `CALL_DATA_INBOUND_UPDATE` payload and sent to the n8n backend webhook without altering the payload schema.
- Files: `mantra/agent.py`, `mantra/utils.py`, `mantra/knowledge_base.py`

## 2026-08-03

### Trunk-Based Call Capacity Gating
- **refactor:** Replaced per-provider capacity (`PROVIDER_MAX_CONCURRENCY`) with per-trunk capacity. Each trunk gets an independent limit derived from its provider's default (Plivo=2, Zadarma=3, VoiceLink=5, Twilio=3).
- **refactor:** Room naming changed from `call_{provider}_{call_id}` → `call_{trunk_id}_{call_id}` across webhook handler, Plivo outbound endpoint, and dispatcher.
- **feat:** `_resolve_trunk_limit(trunk_id)` — resolves trunk→provider→limit via in-memory `_TRUNK_TO_PROVIDER` cache, falling back to `_get_provider_from_trunk()` (LiveKit API + Redis cache). Unknown trunks default to limit 1.
- **feat:** `_trunk_at_capacity(trunk_id)` and `_active_per_trunk(rooms, trunk_id)` replace `_provider_at_capacity` and `_active_per_provider`. Counting uses room name prefix matching on `call_{trunk_id}_`.
- **feat:** `_extract_trunk_ids(rooms)` — parses trunk IDs from room names (`call_ST_abc_123` → `ST_abc` by `rsplit("_", 1)`).
- **refactor:** Health check now reports per-trunk capacity (`trunk_capacity_{trunk_id}`) instead of per-provider.
- **refactor:** Middleware gate now uses `_trunk_at_capacity(trunk_id)` — two Plivo trunks each get independent 2-call pool.
- **chore:** Renamed `PROVIDER_MAX_CONCURRENCY` → `PROVIDER_DEFAULT_CONCURRENCY` (twilio limit changed 2→3).
- Files: `mantra/ui_server.py` (lines 64-138, 556-567, 672-690, 2350-2376, 2875), `mantra/dispatcher.py` (lines 51, 187)

### Zombie Room Cleanup
- **feat:** `cleanup_zombie_rooms()` in `mantra/dispatcher.py` — runs every 60s in the dispatcher loop. Lists LiveKit rooms, deletes `call_*` rooms with `num_participants == 0` via `delete_room()`.
- **feat:** One-shot startup cleanup in `ui_server.py` lifespan — identical logic, runs immediately after startup health check. Writes warning log for each zombie deleted.
- Files: `mantra/dispatcher.py` (lines 117-136, 169), `mantra/ui_server.py` (lines 214-232)

### DB Migration — Call Metadata Columns
- **feat:** Added `caller_number` (VARCHAR 20), `called_number` (VARCHAR 20), `trunk_id` (VARCHAR 100) to `call_logs`. Index on `trunk_id`.
- **feat:** `save_call_log_to_db()` in `mantra/utils.py` now accepts and upserts all three columns.
- **feat:** Agent `finalize()` extracts `caller_number` ← `call_payload.call_from`, `called_number` ← `call_payload.client_phone`, `trunk_id` ← `call_payload.call_from_id`.
- **feat:** `_log_blocked_call()` now passes `caller_number` from `payload.call_from` alongside existing `trunk_id` and `phone`.
- Migration: `migrations/add_trunk_fields.sql`

### DB Migration — kb_collections Process/Stage Descriptions
- **feat:** Added `process_description` (TEXT), `stage_description` (TEXT) to `kb_collections`.
- **feat:** Ingest endpoint (`/api/v1/kb/ingest`) extracts first process's `description`/`name` and first stage's `description`/`name` from `process_stage_data` JSON.
- **feat:** `get_or_create_collection()` (abstract + Postgres impl) accepts and upserts both columns.
- **feat:** `list_collections()` returns the new columns.
- Migration: `migrations/add_trunk_fields.sql`
- Files: `mantra/knowledge_base.py` (lines 94, 255, 270), `mantra/ui_server.py` (lines 909-932)

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