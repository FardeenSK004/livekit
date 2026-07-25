# Mantra Voice Agent

[![Built with LiveKit](https://img.shields.io/badge/Built%20with-LiveKit-blue)](https://livekit.io/)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/downloads/)
[![GitHub Repo](https://img.shields.io/badge/GitHub-Repository-black?logo=github)](https://github.com/Mantracare-Org/livekit)

Low-latency **bilingual (English/Hindi)** telephony voice agent on **LiveKit**. It connects SIP carriers to LiveKit rooms, runs a real-time STT → LLM → TTS pipeline (`agent_name=mantra-agent`), serves an org-scoped knowledge base and ops dashboard, and returns post-call artifacts to **MantraAssist** via HMAC-signed webhooks.

---

## Documentation

| Doc | Role |
|-----|------|
| **[`PROJECT.md`](PROJECT.md)** | **Complete developer reference / SSOT** — architecture, APIs, env vars, flows, deploy, security, known issues |
| [`report.md`](report.md) | Restructure verification (verdict: GO WITH CAVEATS) |
| [`obsidian/`](obsidian/Home.md) | Team knowledge vault (detail & history; may lag code) |

Prefer **`PROJECT.md`** over vault notes when they conflict with current code under `app/`.

---

## Quick start

**Prerequisites:** Python ≥3.11, [uv](https://github.com/astral-sh/uv), Redis, PostgreSQL, LiveKit credentials, and provider keys (see [PROJECT.md §14](PROJECT.md#14-configuration)).

```bash
uv sync
# Copy/configure .env.local (never commit secrets)
# Apply migrations/*.sql to your Postgres DB
./dev.sh
```

If port **8081** is already taken (common on hosts with phpMyAdmin):

```bash
PORT=8091 ./dev.sh
```

Then open `http://localhost:8091` (or `:8081` by default). Note: `dev.sh` status lines always print `:8081` even when `PORT` differs — use the port you set.

| URL | Purpose |
|-----|---------|
| `http://localhost:$PORT` | Login / UI |
| `POST /api/v1/webhooks/telephony` | Outbound call trigger |
| `GET /health` | UI liveness |

**`./dev.sh` starts:** MCP · Agent (`dev`) · UI (`app.main`) · Dispatcher (`app.routines`).

**Console scripts** (`pyproject.toml`):

| Script | Module |
|--------|--------|
| `mantra-ui` / `app-ui` | `app.main` |
| `mantra-agent` / `app-agent` | `app.agent.entrypoint` |
| `app-dispatcher` | `app.routines` |

Individual processes:

```bash
uv run python -m app.main
uv run python -m app.agent.entrypoint dev   # or: start
uv run python -m app.routines
uv run python mcp/server.py
```

---

## Architecture (brief)

Three long-running processes plus optional MCP:

1. **UI / API** (`app.main`) — FastAPI: telephony webhooks, SIP CRUD, dashboard, KB APIs, static UI
2. **Agent worker** (`app.agent.entrypoint`) — LiveKit jobs; STT/LLM/TTS; tools; post-call finalize
3. **Dispatcher** (`app.routines`) — Redis `queue:pending` capacity loop + zombie cleanup
4. **MCP** (`mcp/server.py`) — optional Postgres tools over stdio

Outbound telephony webhooks currently **dispatch immediately** (not via the Redis queue). Full diagrams, flows, and caveats: **[PROJECT.md §4–§9](PROJECT.md#4-high-level-architecture)**.

---

## Repository layout

```
app/           # Production package (routers, agent, kb, dispatcher, services, …)
prompts/       # Markdown system / handoff / analysis prompts
static/        # Dashboard, console, login (served by FastAPI)
migrations/    # SQL schemas (kb_pages, call_logs, org_configs)
mcp/           # MCP Postgres server
config/        # inbound_mappings.json, voices.json
scripts/       # Optional migration helpers
tests/         # pytest suite
obsidian/      # Team vault
PROJECT.md     # Developer SSOT
report.md      # Verification report
dev.sh         # Local all-in-one runner
entrypoint.sh  # Docker process modes
```

Legacy `mantra/` was removed in the restructure; all production code lives under `app/`.

---

## Tech stack

- **Runtime:** Python ≥3.11 · `uv` · FastAPI + Uvicorn
- **Realtime:** LiveKit Agents ~1.4 · Silero VAD + multilingual turn detector
- **STT:** Deepgram Nova-3 (`hi` multilingual)
- **LLM:** OpenAI GPT-4o-mini (default); Gemini / DeepSeek via call metadata
- **TTS:** Cartesia Sonic-3 via LiveKit Inference
- **KB:** PostgreSQL **full-text search** on `kb_pages` (not vector embeddings in current code)
- **Coord / storage:** Redis · AWS S3 (recordings) · LiveKit Cloud SIP
- **Frontend:** Static HTML/JS under `static/`

---

## Deployment

Docker image uses `entrypoint.sh` modes: `agent` (default), `ui`, `dispatcher`, `mcp`.

```bash
docker build -t lkt-mantra .
docker run --env-file .env.local lkt-mantra agent
docker run --env-file .env.local -p 8081:8081 lkt-mantra ui
docker run --env-file .env.local lkt-mantra dispatcher
docker run --env-file .env.local lkt-mantra mcp
```

Apply `migrations/*.sql` before relying on KB, call logs, or org configs. Production roles, health checks, and scaling notes: **[PROJECT.md §17](PROJECT.md#17-deployment)**.

---

## Testing

```bash
uv run python -m pytest
# or: uv run python -m pytest tests/ -v
```

Restructure smoke results and caveats are in [`report.md`](report.md).

---

## Contributing & docs

1. Read **[`PROJECT.md`](PROJECT.md)** for APIs, env vars, and conventions.
2. Use the vault at [`obsidian/Home.md`](obsidian/Home.md) for sprint/history; update Changelog / Current Sprint when you change behavior.
3. Keep secrets in `.env` / `.env.local` — never commit them.
4. Prefer `app/` packages and `migrations/*.sql`; do not revive a `mantra/` tree.

---

## License

Proprietary — Mantracare-Org internal use.
