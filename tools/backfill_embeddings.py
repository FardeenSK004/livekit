#!/usr/bin/env python3
"""
Backfill embeddings for existing kb_pages rows using Google Gemini.

Generates 1536-dim embeddings (matching migration 006) for every row that
has no embedding yet. Idempotent and resumable: rows with an existing
embedding are skipped, so re-running after a failure continues from where
it stopped.

USAGE:
    python tools/backfill_embeddings.py                # backfill all missing
    python tools/backfill_embeddings.py --kb-id 77     # backfill a single kb
    python tools/backfill_embeddings.py --dry-run      # print what would be done
    python tools/backfill_embeddings.py --batch-size 50
    python tools/backfill_embeddings.py --limit 100

Requires POSTGRES_* and GOOGLE_API_KEY in .env.local

NOTE: On Docker-only deployments, run the backfill over HTTP instead:
    POST /api/v1/kb/backfill-embeddings
(see mantra/ui_server.py)
"""
import argparse
import asyncio
import os
import sys
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv(".env.local")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mantra.knowledge_base import PostgresKnowledgeBase


async def run(args):
    dsn = (
        f"postgresql://{os.getenv('POSTGRES_USER')}:{quote_plus(os.getenv('POSTGRES_PASSWORD') or '')}"
        f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
    )
    kb = PostgresKnowledgeBase(dsn)
    try:
        summary = await kb.backfill_embeddings(
            kb_id=args.kb_id,
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
            progress=print,
        )
    finally:
        await kb.close()

    print(
        f"Found {summary['found']} rows missing embeddings"
        + (f" for kb_id={args.kb_id}" if args.kb_id else "")
    )
    if args.dry_run:
        print("Dry run complete — nothing was changed.")
        return
    print(f"Done. {summary['done']} embedded, {summary['failed']} failed.")


def main():
    parser = argparse.ArgumentParser(description="Backfill KB embeddings")
    parser.add_argument("--kb-id", default=None, help="Only backfill rows with this kb_id")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
