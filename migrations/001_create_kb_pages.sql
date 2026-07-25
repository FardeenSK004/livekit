-- Extracted from mantra/migrations/001_kb_pages.py
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
