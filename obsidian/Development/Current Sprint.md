# Current Sprint

> **Sprint:** N/A (no formal sprint process)  
> **Last Updated:** 2026-07-26  
> **Status:** Active maintenance + incremental features

## Recently Completed

- [x] TOS telemetry cleanup — structured `data` payload, natural language stage messages, stripped verbose logging
- [x] Timezone fix — `next_call_on` sent in UTC for scheduled times, rest stays local
- [x] TOS telemetry pipeline — `report_telemetry()` in utils.py, integrated across agent/dispatcher/ui_server
- [x] Health gate middleware — blocks dispatch on dependency failure (HTTP 503)
- [x] Startup healthcheck — parallel checks on all services at boot
- [x] Redis dedup lock on webhook endpoints — prevents duplicate call processing
- [x] Room participant duplicate guard in SIP failure handler
- [x] `send_to_backend` URL fix (`/webhooks/n8n` → `/api/v1/webhooks/n8n`)

## Recently Completed

- [x] Post-call data & timestamps — TOS delivery fix, `next_call_on` format, explicit timestamp fields for n8n

## In Progress

- [ ] Migrate remaining `mantra/agent.py` tool callbacks to separate module
- [ ] Set up automated test suite (currently manual only)

## Previously Completed

- [x] Race condition fix v2: lock TTL 30→600s + duplicate room guard + agent Redis trust fix — 2026-07-24
- [x] Race condition fix v1: Redis dedup lock + null safety + logger fix — 2026-07-24
- [x] Cartesia TTS migration to LiveKit Inference — 2026-06
- [x] Dynamic tone/style configurations for agent prompts — 2026-06
- [x] `end_call` tool with graceful disconnect — 2026-05
- [x] Automated crash email notifications — 2026-05
- [x] Webhook-based call log storage — 2026-05

## Blocked

- Plivo proxy routing stability (India infra) — awaiting provider feedback
