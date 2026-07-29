CREATE TABLE IF NOT EXISTS webhook_events (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(255) UNIQUE NOT NULL,
    call_id VARCHAR(255),
    queue VARCHAR(50) NOT NULL,            -- 'processing' or 'delivery'
    status VARCHAR(50) NOT NULL DEFAULT 'received',
                                           -- received -> processing -> processed -> delivering -> delivered / failed
    payload JSONB NOT NULL,
    result_payload JSONB,                  -- filled after processing completes
    error_message TEXT,
    attempts INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_webhook_events_status ON webhook_events(status);
CREATE INDEX IF NOT EXISTS idx_webhook_events_call_id ON webhook_events(call_id);
