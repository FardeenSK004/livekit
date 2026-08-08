#!/usr/bin/env python3
"""
Migration 006: English-stemmed FTS + pgvector semantic search prep.

1. Rebuilds kb_pages.text_search with the `english` config so inflections
   (e.g. "diagnostic codes" vs "diagnostic code") are stemmed and match.
2. Enables the pgvector extension and adds an `embedding` column
   (vector(1536) for gemini-embedding-2 at 1536 dims) with an HNSW index.

   NOTE: pgvector HNSW/IVFFlat indexes cap at 2000 dimensions, so we request
   1536-dimensional embeddings from Gemini (supported) to stay indexable.

   Embeddings themselves are backfilled separately (tools/backfill_embeddings.py)
   so existing rows stay searchable via FTS in the meantime.
"""

import os
import asyncio
import asyncpg
import logging
from dotenv import load_dotenv

load_dotenv(".env.local")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EMBEDDING_DIM = int(os.getenv("KB_EMBEDDING_DIM", "1536"))


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
        logger.info("Enabling pgvector extension...")
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        except Exception as e:
            logger.warning(f"Could not enable pgvector extension (will continue FTS-only): {e}")

        logger.info("Rebuilding kb_pages.text_search with english config...")
        await conn.execute("ALTER TABLE kb_pages DROP COLUMN IF EXISTS text_search;")
        await conn.execute("""
            ALTER TABLE kb_pages
            ADD COLUMN text_search tsvector
            GENERATED ALWAYS AS (
                to_tsvector('english', coalesce(title, '') || ' ' || coalesce(content_in_text, ''))
            ) STORED;
        """)

        logger.info("Recreating GIN index on text_search...")
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_kb_pages_fts
            ON kb_pages USING GIN (text_search);
        """)

        logger.info(f"Adding embedding column (vector({EMBEDDING_DIM}))...")
        await conn.execute(f"""
            ALTER TABLE kb_pages
            ADD COLUMN IF NOT EXISTS embedding vector({EMBEDDING_DIM});
        """)

        logger.info("Creating HNSW index on embedding...")
        try:
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_kb_pages_embedding
                ON kb_pages USING hnsw (embedding vector_cosine_ops);
            """)
        except Exception as e:
            logger.warning(f"Could not create HNSW index (vector unavailable): {e}")

        logger.info("Migration 006 completed successfully!")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_migration())
