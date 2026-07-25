-- call_logs table used by post-call finalization
CREATE TABLE IF NOT EXISTS call_logs (
    call_id       TEXT PRIMARY KEY,
    call_log      TEXT,
    status        TEXT,
    recording_url TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
