# Post-Call Processing

**Files:** `mantra/agent.py`, `mantra/utils.py`

## Pipeline (in `agent.py` `finalize()`)

1. **Cancel background tasks** — Limiter, inactivity monitor, safety net, transcript logger
2. **Capture history snapshot** — Copy chat messages before session cleanup
3. **Determine call status** — Priority: user_joined + ring time > user_spoke; yields No Answer, Busy, Incomplete, Failed, or Completed
4. **Stop recording & upload to S3** — Mix tracks → trim silence → MP3 → S3
5. **Build transcript** — JSON array of `{bot/user: message}`
6. **LLM analysis** — `analyze_call()` generates summary, process_id, stage transition, sentiment, appointment data (with IST timezone conversion). Uses KB-tracked `process_stage_data` for process-aware analysis. Skipped for Busy/No Answer/Incomplete calls.
7. **Build webhook payload** — Direction-aware: `CALL_DATA_UPDATE` (outbound) or `CALL_DATA_INBOUND_UPDATE` (inbound) with appropriate fields
8. **Save to PostgreSQL** — `save_call_log_to_db()` upsert
9. **Send to backend** — HMAC-signed POST to MantraAssist `/api/v1/webhooks/n8n` with 3 retries
10. **TOS telemetry** — Post-call summary with call_status, duration, S3 status, transcript flag

## SessionRecorder (`utils.py`)

In-memory audio recording system:
- `start_recording(track, label)` — Async consumer per audio track
- `stop_recording()` — Cancel all consumers
- `get_combined_mp3_bytes()` — Mix tracks via numpy, trim silence via pydub, export 128k MP3

## Analyze Call (`utils.py:analyze_call()`)

LLM-driven call analysis with process-aware staging:
- Generates summary paragraph
- Determines process_id from KB-tracked process_stage_data
- Determines CRM stage transition
- Extracts: appointment_date_time (converted to IST), next_call_on, doctor, hospital_location, sentiment_score
- Falls back to heuristics on LLM failure
- Auto-sets next_call_on = +24h for follow-up/callback stages when missing

## Webhook Delivery

- HMAC-SHA256 signed (`x-signature` header)
- 3 retries with exponential backoff (2^N seconds)
- Timestamp-based replay protection (`x-timestamp`)
- Inbound payloads carry: `org_id`, `call_recording`, `process_id` (from KB), `new_stage_id`, `client_phone_number`, `next_call_on`, `called_on`
- Outbound payloads carry: `client_id`, `call_id`, `call_status`, `ai_summary`, `recording_url`, `call_duration_seconds`, `new_stage_id`, `client_custom_fields`

## KB Document Tracking

`KnowledgeRetriever` tracks `accessed_pages_meta` from every KB search during the call. `AssistantFunctions.used_kb_process_ids` extracts unique `process_id` values from accessed pages. For inbound calls, the first unique process_id is injected into the webhook's `process_id` field.
