"""KB schema management — DDL extracted from mantra/migrations."""

KB_PAGES_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS kb_pages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kb_id           TEXT NOT NULL,
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,
    source_type     TEXT NOT NULL,
    page_meta       JSONB DEFAULT '{}',
    content_in_text TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    text_search     tsvector GENERATED ALWAYS AS (
                        to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(content_in_text, ''))
                    ) STORED
);
CREATE INDEX IF NOT EXISTS idx_kb_pages_kb_id ON kb_pages (kb_id);
CREATE INDEX IF NOT EXISTS idx_kb_pages_fts ON kb_pages USING GIN (text_search);
"""

ORG_CONFIGS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS org_configs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            TEXT NOT NULL,
    phone_number      TEXT NOT NULL UNIQUE,
    name              TEXT,
    prompt            TEXT,
    voice             TEXT DEFAULT 'arushi',
    model             TEXT DEFAULT 'deepseek',
    kb_tags           TEXT[] DEFAULT '{}',
    transfer_numbers  JSONB DEFAULT '{}',
    client_name       TEXT DEFAULT 'User',
    process_id        TEXT,
    sip_trunk_id      TEXT,
    dispatch_rule_id  TEXT,
    is_active         BOOLEAN DEFAULT true,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_org_configs_org_id ON org_configs (org_id);
CREATE INDEX IF NOT EXISTS idx_org_configs_active ON org_configs (phone_number, is_active);
"""

CALL_LOGS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS call_logs (
    call_id       TEXT PRIMARY KEY,
    call_log      TEXT,
    status        TEXT,
    recording_url TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
"""
