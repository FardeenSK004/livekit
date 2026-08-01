# Repository Map

```
/home/assassinsk004/livekit/
├── mantra/                        # Core Python application package
│   ├── __init__.py               # Version string
│   ├── agent.py                  # LiveKit voice agent (1629 lines) ★
│   ├── ui_server.py              # FastAPI web/API server (3613 lines) ★
│   ├── dispatcher.py             # Redis queue-based call dispatcher (223 lines)
│   ├── knowledge_base.py         # Postgres FTS knowledge base (561 lines) ★
│   ├── retriever.py              # KB retriever with session cache (58 lines)
│   ├── utils.py                  # S3, DB, recording, analysis, telemetry helpers (595 lines)
│   └── email_alerts.py           # SMTP crash alerts with memes (244 lines)
│
├── mcp/                          # Model Context Protocol server
│   ├── server.py                 # Postgres tools (1073 lines)
│   └── README.md                 # MCP server docs
│
├── static/                       # Frontend (no build step)
│   ├── index.html                # Test console (475 lines)
│   ├── app.js                    # WebRTC client (253 lines)
│   ├── dashboard.html            # Operations dashboard (577 lines)
│   ├── dashboard.js              # Dashboard client (206 lines)
│   ├── login.html                # Auth page (259 lines)
│   ├── kb_chat.html              # KB test chat page
│   └── network.html              # Network monitoring page
│
├── obsidian/                     # This knowledge base ★
├── .planning/                    # Pre-vault internal planning docs
├── Dockerfile                    # Multi-stage Docker build
├── entrypoint.sh                 # agent|ui|mcp mode selector
├── dev.sh                        # Local development launcher
├── pyproject.toml                # Python project config
├── livekit.toml                  # LiveKit Cloud project config
├── uv.lock                       # Dependency lockfile
├── .env.local                    # Active secrets (gitignored)
├── .env                          # Template env (commented)
├── .gitignore
├── .python-version               # 3.12
└── README.md
```

## Key Architecture: Line Count

| File | Lines | % of Codebase |
|------|-------|---------------|
| `mantra/ui_server.py` | 3613 | 41% |
| `mantra/agent.py` | 1629 | 18% |
| `mcp/server.py` | 1073 | 12% |
| `static/dashboard.html` | 577 | 7% |
| `mantra/utils.py` | 595 | 7% |
| `mantra/knowledge_base.py` | 561 | 6% |
| `static/index.html` | 475 | 5% |
| `static/login.html` | 259 | 3% |
| `static/app.js` | 253 | 3% |
| `mantra/email_alerts.py` | 244 | 3% |
| `mantra/dispatcher.py` | 223 | 3% |
| `static/dashboard.js` | 206 | 2% |
| `mantra/retriever.py` | 58 | <1% |
