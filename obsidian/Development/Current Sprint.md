# Current Sprint

> **Sprint:** N/A (no formal sprint process)  
 > **Last Updated:** 2026-07-25  
 > **Status:** Restructure cutover + final verification complete on `feature/restructure` (**GO WITH CAVEATS**)

## In Progress

- [ ] **BLOCKER:** Fix MCP server — `CstdioServerParameters` attribute missing in `livekit.agents.llm.mcp` (upstream API changed)
- [ ] **BLOCKER:** Ingest KB data for org 66 — `kb_pages` table has zero rows for this org
- [ ] Fix post-call webhook 404 — n8n endpoint missing on ngrok backend
- [ ] Fix handoff TTS glitch — silence instructions race with tool return producing `"..."` utterance
- [ ] Set `AWS_S3_BUCKET_NAME` or suppress recording errors
- [ ] Complete `.env.local` for local runs — missing `POSTGRES_*`, `JWT_SECRET`, `ADMIN_*_HASH`, `SIP_TRUNK_ID`; map `GOOGLE_API_KEY`→`GEMINI_API_KEY` and `CARTESIA_API_KEY_2/3`→`CARTESIA_API_KEYS`
- [ ] Note: host port `8081` may be occupied (phpMyAdmin) — use `PORT=8091` locally
- [ ] Pre-merge: staged real SIP call smoke after env + MCP

## Recently Completed

- [x] **2026-07-25** — Final restructure verification (**GO WITH CAVEATS**) — unit 7/7, endpoint smoke 39/39; full write-up in [[Development/Restructure Verification Report.md|Restructure Verification Report]] and repo-root `report.md`
- [x] **2026-07-25** — Verification fixes: dashboard JWT wired; telephony invalid JSON → 400
- [x] **2026-07-25** — README project structure / Docker migration paths updated off `mantra/`
- [x] **2026-07-25** — Codebase Restructure Phases 4–8 complete on `feature/restructure`
  - Phase 4: Full SIP/webhook/dashboard/KB routers in `app/routers/*` + `app/main.py` (55 routes)
  - Phase 5: Full agent port to `app.agent.entrypoint` (`agent_name=mantra-agent`)
  - Phase 6: Dispatcher + zombie cleanup under `app/dispatcher` + `app/routines`
  - Phase 7: KB engine/chunker/retriever/ingestion under `app/kb/`
  - Phase 8: Entrypoints switched, pytest added, static copied, `mantra/` deleted
- [x] **2026-07-23** — Fixed Plivo inbound call: migrated from Plivo Application XML → Plivo Zentrunk SIP trunking
- [x] **2026-07-21** — Fixed inbound call webhook payload: now includes `direction` and `inbound_context`
- [x] **2026-07-21** — Fixed MCP `call_logs` tool
- [x] **2026-07-17** — Fix Knowledge Base ingestion UTF8 encoding errors
- [x] Cartesia TTS migration to LiveKit Inference — 2026-06
- [x] Dynamic tone/style configurations for agent prompts — 2026-06
- [x] `end_call` tool with graceful disconnect — 2026-05
- [x] Automated crash email notifications — 2026-05
- [x] Webhook-based call log storage — 2026-05

## Inbound Call Review (2026-07-22)

Live Plivo call vetted end-to-end. **Inbound flow is solid.** Issues found are in periphery:

| Area | Verdict | Issue |
|------|---------|-------|
| Inbound webhook (Plivo → FastAPI) | ✅ | Works |
| Inbound context resolution (DB) | ✅ | Resolved org 66 from phone number |
| Agent deployment (LiveKit) | ✅ | Room created, agent answered |
| STT / LLM / TTS pipeline | ✅ | Full conversation cycled |
| KB search | ❌ | No data for org 66 |
| Handoff (`transfer_to_human`) | ✅ (w/ glitch) | SIP participant added, but `"..."` TTS error |
| Post-call webhook | ❌ | 404 to n8n |
| Recordings | ❌ | S3 not configured |
