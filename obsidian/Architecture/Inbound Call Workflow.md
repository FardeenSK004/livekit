# Inbound Call Workflow

## Architecture & Flow

```
Step 1: TELEPHONY INGESTION (Zadarma / Twilio / Plivo / VoiceLink)
  ├── External caller dials phone number
  └── Provider forwards SIP INVITE to LiveKit SIP trunk (matched by phone number)

Step 2: LIVEKIT DISPATCH
  ├── LiveKit matches SIP dispatch rule
  ├── Spawns `mantra-agent` in a new room with metadata payload:
  │   └── { "direction": "inbound", "phone_number": "+1..." }
  └── Agent process starts (`mantra/agent.py`)

Step 3: CONTEXT RESOLUTION (Database Fast Path — DB only)
  ├── `resolve_inbound_context(phone_number)` in `agent.py`
  ├── Queries PostgreSQL `org_configs` table (`phone_number` / clean number lookup)
  │   └── Returns: org_id, prompt, voice, model, transfer_numbers, client_name, process_id
  └── Also queries `kb_collections` for all collection UUIDs for this org

Step 4: KB & PROMPT SCOPING
  ├── `org_id` appended as legacy kb_id fallback
  ├── All `kb_collection` UUIDs included as kb_ids
  ├── `kb_tags` loaded for sub-scoping
  ├── System prompt, voice model, and client name configured
  └── `AssistantFunctions` initialized with scoped `kb_ids` and `kb_tags`

Step 5: REAL-TIME CONVERSATION (STT → LLM → TTS)
  ├── STT: Deepgram Nova-3 (`language=multi`)
  ├── Language matching: reply in caller's language each turn (EN/HI)
  ├── LLM: DeepSeek / GPT-4o-mini
  ├── TTS: LiveKit native sonic-3
  └── Tools: `search_knowledge_base` (PostgreSQL FTS), `end_call`

Step 6: POST-CALL PROCESSING
  ├── Session recorder captures transcript & audio
  ├── MP3 mixed & uploaded to AWS S3
  ├── LLM analysis (summary, sentiment, stage transition, process_id from KB, user_intent)
  ├── Inbound webhook: `CALL_DATA_INBOUND_UPDATE` — `user_intent` set to `"APPOINTMENT_BOOKED"` iff appointment booked AND outcome stage is appointment booking stage from KB (else null); `org_id`/`process_id`/`new_stage_id` coerced string→int (null if missing)
  └── Call log saved to PostgreSQL `call_logs` table
```

## Related Files
- `mantra/agent.py` — Inbound resolution, LLM prompt generation, agent entrypoint
- `mantra/ui_server.py` — SIP setup, dispatch rule creation, `org_configs` management
- `mantra/knowledge_base.py` — PostgreSQL FTS search and page storage (`kb_pages` + `kb_collections`)

