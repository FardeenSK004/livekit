# Database Schema

## PostgreSQL Database

The application uses a single table `call_logs` in an isolated database.

### Table: `call_logs`

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL PRIMARY KEY | Auto-increment ID |
| `call_id` | TEXT UNIQUE NOT NULL | Unique call identifier |
| `call_log` | JSONB | Complete call data payload |
| `status` | TEXT | Call status (Completed, Busy, No Answer, Error, Incomplete) |
| `recording_url` | TEXT | S3 URL of recording |
| `caller_number` | VARCHAR(20) | Calling number (SIP trunk Caller ID) |
| `called_number` | VARCHAR(20) | Called number (client phone) |
| `trunk_id` | VARCHAR(100) | LiveKit SIP Trunk ID used for the call |
| `created_at` | TIMESTAMPTZ DEFAULT NOW() | Record creation timestamp |

**Queries:**
- Insert/update: `INSERT ... ON CONFLICT (call_id) DO UPDATE SET ...`
- Dashboard metrics: Aggregation by status with duration averaging
- Call history: Paginated listing with JSONB field extraction

### Table: `kb_pages`

Full-Text Search table for Knowledge Base document chunks (uses PostgreSQL `tsvector`).

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PRIMARY KEY | Auto-generated UUID |
| `kb_id` | TEXT | Collection UUID (maps to `kb_collections.id`) or org ID for legacy data. Which KB collection this chunk belongs to. |
| `title` | TEXT | Document title |
| `content` | TEXT | Original source (filename or URL) |
| `source_type` | TEXT | e.g. `file`, `text`, `url` |
| `page_meta` | JSONB | Metadata: strategy, chunk_index, document_id, tags_name, process_id, stage_id, s3_url |
| `content_in_text` | TEXT | Plain text content of the chunk (what the LLM sees) |
| `created_at` | TIMESTAMPTZ DEFAULT NOW() | Record creation timestamp |
| `text_search` | tsvector (generated) | `to_tsvector('simple', title || ' ' || content_in_text)` — auto-populated |

**Indexes:** B-tree on `(kb_id)`, GIN on `(text_search)` for FTS.

### Table: `kb_collections`

Groups KB pages into named collections per org. One collection = one document.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PRIMARY KEY | Auto-generated UUID, used as `kb_pages.kb_id` |
| `org_id` | TEXT NOT NULL | Organization that owns this collection |
| `document_id` | TEXT NOT NULL | Unique document identifier per org |
| `name` | TEXT | Display name (filename or doc ID) |
| `description` | TEXT | Optional description |
| `process_description` | TEXT | Main process description from `process_stage_data` |
| `stage_description` | TEXT | First stage description from `process_stage_data` |
| `process_id` | INT | Process identifier linked to this KB collection |
| `stage_id` | INT | Initial / primary stage identifier |
| `stage_ids` | INT[] | Array of associated stage identifiers |
| `process_assignments` | JSONB | Raw process assignment array `[{"process_id": int, "stage_ids": [int]}]` |
| `created_at` | TIMESTAMPTZ DEFAULT NOW() | Creation timestamp |

**Constraints:** `UNIQUE(org_id, document_id)` — one collection per document per org.
**Indexes:** B-tree on `(org_id)`.

### Table: `org_configs`

### Table: `org_configs`

Maps an inbound phone number to an organization and provides its specific agent configuration.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PRIMARY KEY | Auto-generated UUID |
| `org_id` | TEXT | Identifier linking to the organization (and its KB) |
| `phone_number` | TEXT UNIQUE | The inbound DID number |
| `name` | TEXT | Display name for the mapping |
| `prompt` | TEXT | System prompt instructing the agent |
| `voice` | TEXT | Agent voice (e.g., 'arushi') |
| `model` | TEXT | LLM model (e.g., 'deepseek') |
| `kb_tags` | TEXT[] | Specific KB tags to restrict search within the org |
| `transfer_numbers` | JSONB | Mapping of departments to phone numbers |
| `client_name` | TEXT | Default caller name |
| `process_id` | TEXT | External process/workflow identifier |
| `sip_trunk_id` | TEXT | Associated LiveKit SIP Trunk ID |
| `dispatch_rule_id` | TEXT | Associated LiveKit SIP Dispatch Rule ID |
| `is_active` | BOOLEAN | Whether this mapping is currently active |
| `created_at` | TIMESTAMPTZ | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | Last update timestamp |

### KB Resolution Flow

When an inbound call arrives, the agent resolves KB scope for the org:

1. Look up `org_configs` by phone number → get `org_id`
2. Query `kb_collections WHERE org_id = ?` → get all collection UUIDs
3. Include the `org_id` itself as a fallback (backward compat with legacy data)
4. Search `kb_pages WHERE kb_id = ANY([collection_uuids..., org_id])`

This means one org = multiple KBs (collections). Each ingested document creates its own collection, and the agent searches across all collections for that org.

### Connection

Managed via `asyncpg`. Connection parameters from environment:
```
POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_HOST, POSTGRES_PORT
```

Default port mapping: `5433` (local `lkdb` docker-compose) / `5432` (container internal)

---

## Redis Data Structures

| Key Pattern | Type | Purpose | TTL |
|-------------|------|---------|-----|
| `queue:pending` | Sorted Set | Call queue (score = priority) | — |
| `calls:active` | Hash | `call_id → room_name` | — |
| `calls:status:{call_id}` | String | Per-call status | — |
| `lock:call:{call_id}` | String | Dedup lock for webhooks | 600s |
| `sip_error_status:{call_id}` | String | SIP failure classification (No Answer / Busy / Incomplete) | 300s |
| `trunk:provider:{trunk_id}` | String | Cached trunk→provider mapping | 30d |
| `{provider}:sip_trunk:{number}` | String | Provider SIP trunk mapping | 30d |

Connection via `REDIS_URL` env var.
