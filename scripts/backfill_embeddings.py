"""CLI script to backfill vector embeddings for all KB pages."""

import os
import asyncio
import logging
from dotenv import load_dotenv

load_dotenv(".env.local")
load_dotenv()

from core.kb.knowledge_base import PostgresKnowledgeBase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scripts.backfill")


async def main():
    dsn = (
        f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
        f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
    )
    kb = PostgresKnowledgeBase(dsn)
    logger.info("Starting KB embeddings backfill...")
    updated = await kb.backfill_embeddings(limit=500)
    logger.info(f"Backfill complete. Updated {updated} chunks.")


if __name__ == "__main__":
    asyncio.run(main())
