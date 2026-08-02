# Glossary

| Term | Definition |
|------|------------|
| **Agent** | LiveKit voice agent (`mantra/agent.py`) that processes real-time voice conversations |
| **Deepgram** | STT provider (Nova-3) for speech recognition; configured with `language="multi"` for EN/HI/Hinglish |
| **Dispatcher** | Background process that dequeues calls from Redis and dispatches to LiveKit (legacy queue path) |
| **HMAC** | Hash-based Message Authentication Code used for webhook signing |
| **LiveKit** | WebRTC infrastructure platform for real-time audio/video |
| **MCP** | Model Context Protocol — exposes PostgreSQL tools to AI agents |
| **Plivo** | Telephony provider for India (requires proxied API + Zentrunk for inbound) |
| **Silero VAD** | Voice Activity Detection model (PyTorch) |
| **SIP Trunk** | SIP connection to telephony provider (Twilio, Plivo, Zadarma, VoiceLink) |
| **sonic-3** | LiveKit native TTS model, no external API dependency |
| **SSE** | Server-Sent Events — used for real-time dashboard updates |
| **STT** | Speech-to-Text |
| **TOS** | Telemetry Observability Service — structured logging endpoint for operational monitoring |
| **TTS** | Text-to-Speech — rendered via LiveKit native `sonic-3` |
| **Turn Detection** | Detects when a speaker has finished their turn (MultilingualModel) |
| **Twilio** | Primary telephony provider (US) |
| **VAD** | Voice Activity Detection — detects when someone is speaking |
| **VoiceLink** | LiveKit-native SIP provider for outbound/inbound calls |
| **Zadarma** | Telephony provider (default fallback) |
| **Zentrunk** | Plivo's SIP trunking product used for inbound call routing |
