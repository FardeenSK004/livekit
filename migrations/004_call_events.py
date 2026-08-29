"""
Migration 004: call_events table — per-stage call lifecycle audit log.

Each row captures one event in a call's lifecycle with full payload detail.
call_id + event_type are compound-unique so each event type appears once per call.
"""

import os
import logging
import asyncpg
from dotenv import load_dotenv

load_dotenv(".env.local")  # allows override
load_dotenv(".env")

logger = logging.getLogger("mantra.migrations.004_call_events")

MIGRATION_ID = "004_call_events"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS call_events (
    id              SERIAL PRIMARY KEY,
    call_id         VARCHAR(64)  NOT NULL,
    event_type      VARCHAR(32)  NOT NULL,
    event_source    VARCHAR(16)  NOT NULL,
    event_payload   JSONB        NOT NULL DEFAULT '{}'::jsonb,
    event_log       TEXT         NOT NULL DEFAULT '',
    event_status    VARCHAR(16)  NOT NULL DEFAULT 'success',
    event_error     TEXT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (call_id, event_type)
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_call_events_call_id ON call_events (call_id);
CREATE INDEX IF NOT EXISTS idx_call_events_created_at ON call_events (created_at);
CREATE INDEX IF NOT EXISTS idx_call_events_type ON call_events (event_type);
"""


async def _run(conn: asyncpg.Connection):
    logger.info(f"[{MIGRATION_ID}] Creating call_events table...")
    await conn.execute(CREATE_TABLE_SQL)
    await conn.execute(CREATE_INDEX_SQL)
    await conn.execute("SELECT setval(pg_get_serial_sequence('call_events', 'id'), COALESCE(MAX(id), 1)) FROM call_events;")
    logger.info(f"[{MIGRATION_ID}] call_events table ready.")


async def migrate():
    db_user = os.getenv("POSTGRES_USER")
    db_password = os.getenv("POSTGRES_PASSWORD")
    db_name = os.getenv("POSTGRES_DB")
    db_host = os.getenv("POSTGRES_HOST")
    db_port = os.getenv("POSTGRES_PORT")

    if not all([db_user, db_password, db_name, db_host, db_port]):
        logger.warning(
            f"[{MIGRATION_ID}] DB env vars missing — skipping migration"
        )
        return

    conn = await asyncpg.connect(
        user=db_user,
        password=db_password,
        database=db_name,
        host=db_host,
        port=db_port,
    )
    try:
        await _run(conn)
    finally:
        await conn.close()
