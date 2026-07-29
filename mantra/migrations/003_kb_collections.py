#!/usr/bin/env python3
"""
Migration script to create kb_collections table for multi-KB per org support.
Each document ingested becomes a separate KB collection under an org.
Run once after 001_kb_pages.py and 002_org_configs.py.
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
        logger.info("Creating kb_collections table...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS kb_collections (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                org_id      TEXT NOT NULL,
                document_id TEXT NOT NULL,
                name        TEXT NOT NULL DEFAULT '',
                description TEXT DEFAULT '',
                created_at  TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(org_id, document_id)
            );
        """)
        logger.info("kb_collections table created successfully")

        logger.info("Creating indexes...")
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_kb_collections_org_id
            ON kb_collections (org_id);
        """)
        logger.info("Indexes created successfully")

        rows = await conn.fetch("""
            SELECT DISTINCT kb_id, page_meta->>'document_id' AS document_id
            FROM kb_pages
            WHERE page_meta->>'document_id' IS NOT NULL
        """)
        count = 0
        for row in rows:
            kb_id = row["kb_id"]
            doc_id = row["document_id"]
            try:
                await conn.execute("""
                    INSERT INTO kb_collections (org_id, document_id, name)
                    VALUES ($1, $2, $2)
                    ON CONFLICT (org_id, document_id) DO NOTHING
                """, kb_id, doc_id)
                count += 1
            except Exception:
                pass
        if count:
            logger.info(f"Seeded {count} collections from existing kb_pages")

        logger.info("Migration 003 completed successfully!")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_migration())
