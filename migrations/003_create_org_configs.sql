-- Extracted from mantra/migrations/002_org_configs.py
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
