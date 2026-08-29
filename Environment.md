# Environment Configuration

This document outlines all environment variables configured across development and production for the Mantra LiveKit Voice Agent & Telephony Backend.

## Core Settings

| Variable | Description | Default |
|---|---|---|
| `PY_ENV` | Environment identifier (`development`, `production`, `staging`, `test`) | `development` |
| `PORT` | FastAPI HTTP web server port | `8081` |
| `AGENT_NAME` | LiveKit agent dispatch identity name | `mantra-agent` |
| `MAX_CONCURRENCY` | Maximum concurrent active voice calls | `5` |
| `BYPASS_HEALTH_CHECKS` | Bypass infrastructure health gates during local dev | `0` |

## LiveKit Cloud

| Variable | Description |
|---|---|
| `LIVEKIT_URL` | LiveKit Server / Cloud WebSocket URL (`wss://...`) |
| `LIVEKIT_API_KEY` | LiveKit Cloud API Key |
| `LIVEKIT_API_SECRET` | LiveKit Cloud API Secret |
| `LIVEKIT_SIP_DOMAIN` | SIP Domain configured for LiveKit SIP Trunks |

## Telephony Providers & Proxies

| Variable | Description |
|---|---|
| `SIP_TRUNK_ID` | Default LiveKit SIP trunk ID |
| `PLIVO_PROXY` | Proxy endpoint for Indian routing with Plivo |
| `VOICELINK_PROXY` | Proxy endpoint for VoiceLink routing |
| `PLIVO_MAX_CONCURRENCY` | Maximum concurrent calls on Plivo trunk (default: `2`) |
| `ZADARMA_MAX_CONCURRENCY` | Maximum concurrent calls on Zadarma trunk (default: `3`) |
| `VOICELINK_MAX_CONCURRENCY` | Maximum concurrent calls on VoiceLink trunk (default: `5`) |
| `TWILIO_MAX_CONCURRENCY` | Maximum concurrent calls on Twilio trunk (default: `3`) |

## LLM & STT/TTS Providers

| Variable | Description |
|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek API key for conversational LLM & post-call analysis |
| `OPENAI_API_KEY` | OpenAI API key for fallback LLM |
| `GOOGLE_API_KEY` | Google Gemini API key for embeddings |
| `DEEPGRAM_API_KEY` | Deepgram API key for speech-to-text |
| `POST_CALL_LLM_MODEL` | Model for post-call analysis (default: `deepseek-v4-pro`) |

## PostgreSQL & Redis

| Variable | Description |
|---|---|
| `POSTGRES_HOST` | PostgreSQL Host |
| `POSTGRES_PORT` | PostgreSQL Port (default: `5432`) |
| `POSTGRES_USER` | PostgreSQL Username |
| `POSTGRES_PASSWORD` | PostgreSQL Password |
| `POSTGRES_DB` | PostgreSQL Database name |
| `DATABASE_URL` | Optional consolidated database connection string |
| `REDIS_URL` | Redis URL for queue and active call tracking |

## AWS S3 & Alerting

| Variable | Description |
|---|---|
| `AWS_ACCESS_KEY_ID` | AWS Access Key for recording upload |
| `AWS_SECRET_ACCESS_KEY` | AWS Secret Key for recording upload |
| `AWS_REGION` | AWS S3 region (default: `us-east-1`) |
| `AWS_S3_BUCKET_NAME` | S3 bucket name for call recordings |
| `ALERT_SMTP_HOST` | SMTP server for crash error alerts |
| `ALERT_SMTP_PORT` | SMTP port (default: `587`) |
| `ALERT_SMTP_USER` | SMTP username |
| `ALERT_SMTP_PASS` | SMTP password |
| `ALERT_EMAIL_TO` | Recipient email for crash notifications |
| `MANTRAASSIST_BACKEND_URL` | URL of the central CRM / backend |
| `MANTRAASSIST_WEBHOOK_SECRET`| Shared HMAC-SHA256 secret for webhook verification |
