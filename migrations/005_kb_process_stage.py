#!/usr/bin/env python3
"""
Migration 005: Add process_id, stage_id, stage_ids, process_assignments,
process_description, and stage_description columns to kb_collections.
"""

import os
import asyncio
import asyncpg
import logging
from dotenv import load_dotenv

load_dotenv(".env.local")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_migration():
    db_user = os.getenv("POSTGRES_USER")
    db_password = os.getenv("POSTGRES_PASSWORD")
    db_name = os.getenv("POSTGRES_DB")
    db_host = os.getenv("POSTGRES_HOST")
    db_port = os.getenv("POSTGRES_PORT")

    if not all([db_user, db_password, db_name, db_host, db_port]):
        raise ValueError("Missing required PostgreSQL environment variables")

    conn = await asyncpg.connect(
        user=db_user,
        password=db_password,
        database=db_name,
        host=db_host,
        port=int(db_port),
        timeout=10.0,
    )

    try:
        logger.info("Adding process and stage columns to kb_collections...")
        await conn.execute("""
            ALTER TABLE kb_collections
            ADD COLUMN IF NOT EXISTS process_id INT,
            ADD COLUMN IF NOT EXISTS stage_id INT,
            ADD COLUMN IF NOT EXISTS stage_ids INT[],
            ADD COLUMN IF NOT EXISTS process_assignments JSONB,
            ADD COLUMN IF NOT EXISTS process_description TEXT,
            ADD COLUMN IF NOT EXISTS stage_description TEXT;
        """)
        logger.info("kb_collections altered successfully")

        logger.info("Creating indexes for process_id and stage_id on kb_collections...")
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_kb_collections_process_id ON kb_collections (process_id);
            CREATE INDEX IF NOT EXISTS idx_kb_collections_stage_id ON kb_collections (stage_id);
        """)
        logger.info("Indexes created successfully")

        logger.info("Migration 005 completed successfully!")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_migration())
