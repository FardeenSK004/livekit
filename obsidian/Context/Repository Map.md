# Repository Map

```
livekit/
├── app/                           # Application package (replaces mantra/)
│   ├── main.py                    # FastAPI factory + lifespan
│   ├── middleware.py              # Prometheus, crash handler, request logging
│   ├── config/                    # Settings, constants, logging, prompts
│   ├── models/                    # Pydantic schemas
│   ├── routers/                   # Thin HTTP routers
│   ├── services/                  # Business logic (LiveKit, Redis, DB, SIP, …)
│   ├── agent/                     # Voice agent + tools
│   ├── kb/                        # Knowledge base engine + ingestion
│   ├── dispatcher/                # Call dispatch worker
│   ├── routines/                  # Dispatcher loop + zombie cleanup
│   ├── recording/                 # SessionRecorder
│   ├── alerter/                   # Crash email alerts
│   ├── stt/ llm/ tts/             # Pipeline helpers
│   └── static/                    # Frontend copy
│
├── mcp/                           # Model Context Protocol server
├── static/                        # Frontend (repo-root; also copied to app/static)
├── prompts/                       # Prompt markdown files
├── config/                        # inbound_mappings.json, voices.json
├── migrations/                    # SQL migrations
├── scripts/                       # Runnable migration helpers
├── tests/                         # pytest suite
├── obsidian/                      # Knowledge vault
├── Dockerfile
├── entrypoint.sh                  # agent|ui|dispatcher|mcp
├── dev.sh
├── pyproject.toml
└── README.md
```

## Entrypoints

| Script / command | Target |
|------------------|--------|
| `mantra-agent` / `app-agent` | `app.agent.entrypoint:run_agent` |
| `mantra-ui` / `app-ui` | `app.main:main` |
| `app-dispatcher` | `app.routines.__main__:main` |
| `./entrypoint.sh agent\|ui\|dispatcher\|mcp` | Docker/process modes |
| `./dev.sh` | Local agent + UI + dispatcher + MCP |
