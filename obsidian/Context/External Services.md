# External Services

## LiveKit Cloud
- **Purpose:** WebRTC infrastructure + SIP trunking
- **Project:** `mantraassist-0ek43ife`
- **Agent ID:** `CA_zni3j8qMiM82`
- **Auth:** API key + secret in `.env.local`
- **Docs:** https://docs.livekit.io

## Deepgram
- **Purpose:** Speech-to-Text (Nova-3)
- **Language:** `multi` (English + Hindi/Hinglish)
- **Auth:** API key in `.env.local`

## OpenAI
- **Purpose:** LLM (GPT-4o-mini)
- **Auth:** API key in `.env.local`

## Google AI
- **Purpose:** LLM (Gemini 2.5 Flash)
- **Auth:** API key in `.env.local`

## DeepSeek
- **Purpose:** LLM (DeepSeek v4 Flash)
- **Endpoint:** `https://api.deepseek.com`
- **Auth:** API key in `.env.local`

## TTS (LiveKit Native)

- **Provider:** LiveKit Inference (no external TTS API dependency)
- **Model:** sonic-3 (native)
- **Voices:** 8 configured in `VOICE_MAPPING`
- **Speed:** Configurable via `voice_speed` (0.1–2.0 range)

## Telephony Providers
- **Twilio** — US/primary SIP trunk
- **Plivo** — India routing (proxied API + Zentrunk for inbound)
- **Zadarma** — Default/fallback
- **VoiceLink** — LiveKit-native provider (proxied, `destination_country="in"`)

## AWS
- **S3** — Recording storage
- **SNS** — Notifications (optional)

## MantraAssist Backend
- **Purpose:** CRM/webhook target for post-call data
- **Auth:** HMAC-SHA256 signing with shared secret

## PostgreSQL
- **Purpose:** Call log persistence, KB storage (kb_pages + kb_collections), org configs
- **Managed:** External `lkdb` docker-compose
- **Default:** Localhost:5433 / Container:5432

## Redis
- **Purpose:** Queue, state, capacity tracking
- **Default:** Localhost:6379
