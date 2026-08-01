# Bugs

## Open

| ID | Description | Module | Severity | Status |
|----|-------------|--------|----------|--------|
| — | **MCP server broken** — `livekit.agents.llm.mcp` missing `CstdioServerParameters` (upstream API change) | `mcp/` | Blocker | Open |
| — | **Handoff TTS glitch** — `"..."` residual utterance after `transfer_to_human` causes traceback | `agent.py` | High | Open (tool disabled as workaround) |
| — | **Post-call webhook 404** — n8n endpoint missing on ngrok backend | `utils.py` | High | Open |
| — | **S3 not configured** — `AWS_S3_BUCKET_NAME` not set, recordings silently dropped | Infra | High | Open |
| — | **No KB data for org 66** — `kb_pages` has zero rows for this org | KB | Blocker | Open |

## Known Issues

| Issue | Impact | Notes |
|-------|--------|-------|
| Zombie calls | Medium | Dispatcher has cleanup but race conditions possible |
| Webhook reliability | Medium | External n8n may be unreachable |
| Monolithic agent.py | Medium | 1,629 lines, hard to maintain |
| No automated tests | High | Regression risk |
| OpenTelemetry suppression | Low | Hides metrics but prevents 429 errors |
| Dispatcher 0.5s polling | Low | Replace with Redis Pub/Sub |
