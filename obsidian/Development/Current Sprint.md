# Current Sprint

> **Sprint:** N/A (no formal sprint process)  
> **Last Updated:** 2026-08-01  
> **Status:** Active maintenance, Multi-KB per org (KB collections), Voicelink SIP inbound trunk provisioning, LiveKit native `sonic-3` TTS, per-provider call capacity gating

## Recently Completed

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
