# Release Notes

## v0.3.0 (Current)

### Core Features
- **Real-time Voice Pipeline** — STT (Deepgram Nova-3) → LLM (OpenAI GPT-4o-mini / Gemini 2.5 Flash / DeepSeek v4 Flash) → TTS (LiveKit native sonic-3)
- **Bilingual EN/HI** — Seamless English/Hindi switching with Hinglish support
- **8 TTS Voices** — arushi, gemma, alistair, sunny, tyler, vikas, camila, renata
- **Knowledge Base RAG** — PostgreSQL FTS with adaptive chunking, multi-KB collections per org
- **end_call Tool** — LLM-controlled graceful call termination with safety net

### Telephony
- **4 SIP Providers** — Twilio, Plivo (India proxy + Zentrunk for inbound), Zadarma, VoiceLink
- **Per-Provider Capacity Gating** — Plivo=2, Zadarma=3, VoiceLink=5, Twilio=2, Global=5
- **SIP Failure Handling** — 408→No Answer, 486→Busy, other→Incomplete; returns 503 to caller
- **End-to-End Inbound SIP Setup** — Trunk + dispatch rule + provider API in one request
- **Inbound + Outbound Support** — DB-based context resolution via `org_configs`
- **Inbound Dispatch Rules** — CRUD + patch endpoints for SIP routing

### Operations
- **FastAPI API Server** — Webhooks, SIP management, KB ingestion, dashboard APIs, health checks
- **JWT Authentication** — SHA-256 hashed credentials, 24h expiry
- **OpsCraft Dashboard** — SSE real-time metrics, active calls, paginated call history
- **Prometheus Metrics** — Via `prometheus_fastapi_instrumentator`
- **PostgreSQL Logging** — Call logs, KB pages/collections, org configs
- **S3 Recordings** — In-memory MP3 mixing with silence trimming
- **HMAC-SHA256 Webhooks** — Signed post-call data delivery with 3 retries
- **TOS Telemetry** — Structured operational logging across all services
- **SMTP Crash Alerts** — Formatted HTML emails with meme images for admins

### MCP Server
- **13 Database Tools** — Patient lookup, doctors, hospitals, appointments (create/update/query), call history, DB schema introspection, call log upsert

### Known Limitations
- No automated test suite
- 3-minute maximum call duration (soft farewell at 2m30s)
- `transfer_to_human` tool disabled (TTS glitch race condition)
- Single admin user
- Dispatcher uses 0.5s polling (Redis Pub/Sub planned)
