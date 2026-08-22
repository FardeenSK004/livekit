# DevOps Agent

## Context

Deployment environment for the Mantra Voice Agent.

## Deployment

### Docker
Multi-stage build (`Dockerfile`):
1. `base` — uv + Python 3.12 slim
2. `build` — Compile dependencies
3. `production` — Runtime with appuser (UID 10001)

Models pre-cached during build (Silero VAD, HuggingFace, Torch).

### Entrypoint
Three modes:
- `agent` — `uv run python -m mantra.agent start`
- `ui` — `uv run python -m mantra.ui_server`
- `mcp` — `uv run python mcp/server.py`

### Docker commands
```bash
docker build -t mantra-agent .
docker run --env-file .env.local mantra-agent agent
docker run --env-file .env.local -p 8081:8081 mantra-agent ui
docker run --env-file .env.local mantra-agent mcp
```

## Infrastructure

| Service | Host | Notes |
|---------|------|-------|
| PostgreSQL | External `lkdb` | Port 5433 (local) / 5432 (container) |
| Redis | localhost:6379 | Queue, state, locks, caching |
| S3 | AWS | Recording storage + KB files |
| LiveKit | Cloud-managed | `mantraassist-0ek43ife` |
| SMTP | Gmail | Crash email alerts |

## Environment Files
- `.env.local` — Active secrets (gitignored, never commit)
- `.env` — Template with commented-out values (safe to commit)
