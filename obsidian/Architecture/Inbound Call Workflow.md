# Inbound Call Workflow

## Architecture & Flow

```
Step 1: TELEPHONY INGESTION (Zadarma / Twilio)
  ├── External caller dials phone number (+1...)
  └── Zadarma/Twilio forwards SIP INVITE to LiveKit SIP trunk (matched by phone number)

Step 2: LIVEKIT DISPATCH
  ├── LiveKit matches SIP dispatch rule
  ├── Spawns `mantra-agent` in a new room with metadata payload:
  │   └── { "direction": "inbound", "phone_number": "+1..." }
  └── Agent process starts (`mantra/agent.py`)

Step 3: CONTEXT RESOLUTION (Database Fast Path & Fallback)
  ├── `resolve_inbound_context(phone_number)` in `agent.py`
  ├── Fast Path: Query PostgreSQL `org_configs` table (`phone_number` / clean number lookup)
  │   └── Returns: org_id, prompt, voice, model, transfer_numbers, client_name
  └── Fallback Path: POST /api/v1/telephony/resolve-inbound-call to MantraAssist backend

Step 4: KB & PROMPT SCOPING
  ├── `org_id` mapped as `kb_id` (`kb_id = org_id`)
  ├── `kb_tags` loaded for sub-scoping
  ├── System prompt, voice model, and client name configured
  └── `AssistantFunctions` initialized with scoped `kb_ids` and `kb_tags`

Step 5: REAL-TIME CONVERSATION (STT → LLM → TTS)
  ├── STT: Deepgram Nova-3 (Hinglish/Multilingual)
  ├── LLM: DeepSeek / GPT-4o-mini
  ├── TTS: LiveKit Inference Sonic-3
  └── Tool: `search_knowledge_base` (PostgreSQL Full-Text Search via `kb_pages` filtered by `kb_id`)

Step 6: POST-CALL PROCESSING
  ├── Session recorder captures transcript & audio
  ├── MP3 mixed & uploaded to AWS S3
  ├── LLM analysis (summary, sentiment, stage transition)
  ├── Webhook delivery to MantraAssist backend
  └── Call log saved to PostgreSQL `call_logs` table
```

## Related Files
- `mantra/agent.py` — Inbound resolution, LLM prompt generation, agent entrypoint
- `mantra/ui_server.py` — SIP setup, dispatch rule creation, `org_configs` management
- `mantra/knowledge_base.py` — PostgreSQL FTS search and page storage (`kb_pages`)
- `obsidian/Untitled.canvas` — Visual node graph of the inbound flow
