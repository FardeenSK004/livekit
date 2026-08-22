# Infrastructure

## LiveKit Cloud

- **Project:** `mantraassist-0ek43ife`
- **Agent ID:** `CA_zni3j8qMiM82`
- **Config:** `livekit.toml`
- Production scaling: 1-2 instances, 1-2 replicas
- SIP trunks configured for Twilio, Plivo, Zadarma, VoiceLink

## Deployment

### Docker

Multi-stage build (`Dockerfile`):
1. `base` — uv + Python 3.12 slim
2. `build` — Compile dependencies
3. `production` — Runtime with appuser (UID 10001)

Models pre-cached during build (Silero VAD, HuggingFace, Torch).

### Entrypoint (`entrypoint.sh`)

Three modes:
- `agent` — `uv run python -m mantra.agent start`
- `ui` — `uv run python -m mantra.ui_server`
- `mcp` — `uv run python mcp/server.py`

### Local Development (`dev.sh`)

Launches both agent + UI server, prints API endpoints.

## Infrastructure Dependencies

| Service | Purpose | Connection |
|---------|---------|------------|
| LiveKit Cloud | WebRTC + SIP trunking | API key/secret |
| PostgreSQL | Call log persistence + KB storage + org configs | `lkdb` docker-compose (5433 local) |
| Redis | Queue + state + capacity + SIP error status | Local (6379) |
| AWS S3 | Recording storage | Bucket + credentials |
| SMTP (Gmail) | Crash email alerts | Gmail app password |
| Deepgram API | Speech-to-text | API key |
| OpenAI API | LLM (GPT-4o-mini) | API key |
| Google AI API | LLM (Gemini) | API key |
| DeepSeek API | LLM (DeepSeek) | API key |
| MantraAssist Backend | CRM webhook target | HTTP + HMAC |
| TOS Endpoint | Telemetry logging | HTTP + Bearer token |
