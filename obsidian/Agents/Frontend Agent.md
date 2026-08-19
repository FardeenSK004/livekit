# Frontend Agent

## Context

Frontend is vanilla HTML/CSS/JS in `static/` — no build step, no framework.

## Key Files

| File | Purpose |
|------|---------|
| `login.html` | JWT login page (dark theme) |
| `dashboard.html` | Operations dashboard — SSE metrics, call history, active calls |
| `index.html` | Test console — LiveKit room connection, WebRTC, transcript |
| `kb_chat.html` | KB text chat testing interface |
| `network.html` | Network monitoring page |
| `app.js` | WebRTC client: room connect, mic toggle, transcript display |
| `dashboard.js` | Dashboard: SSE stream, metrics bars, active call cards, paginated history |

## Design System

- **OpsCraft** dark theme — Discord/Linear-inspired
- CSS variables for theming (`--primary`, `--background`, `--text`, etc.)
- Card-style layouts with glassmorphism effects
- No external CSS libraries

## LiveKit Integration

- LiveKit Client SDK loaded from CDN
- Token obtained from `/dispatch-test` or webhook response
- WebRTC room: join → publish/subscribe audio → display transcript
