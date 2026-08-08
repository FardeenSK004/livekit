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
"""
import argparse
import asyncio
import os
import sys
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv(".env")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mantra.knowledge_base import PostgresKnowledgeBase, _embedding_to_text
from mantra.gemini_embeddings import embed_texts, get_embedding_dim


async def run(args):
    dsn = (
        f"postgresql://{os.getenv('POSTGRES_USER')}:{quote_plus(os.getenv('POSTGRES_PASSWORD') or '')}"
        f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
    )
    kb = PostgresKnowledgeBase(dsn)
    pool = await kb._get_pool()

    where = "embedding IS NULL"
    params = []
    if args.kb_id:
        where += " AND kb_id = $1"
        params.append(args.kb_id)

    async with pool.acquire() as conn:
        supports = await kb._supports_embeddings(conn)
        if not supports:
            print("ERROR: kb_pages.embedding column does not exist. Run migration 006 first.")
            await pool.close()
            sys.exit(1)

        sql = f"SELECT id, content_in_text FROM kb_pages WHERE {where} ORDER BY created_at"
        if args.limit:
            sql += f" LIMIT {args.limit}"
        rows = await conn.fetch(sql, *params)

    print(f"Found {len(rows)} rows missing embeddings" + (f" for kb_id={args.kb_id}" if args.kb_id else ""))
    if args.dry_run:
        await pool.close()
        print("Dry run complete — nothing was changed.")
        return

    dim = get_embedding_dim()
    done = 0
    failed = 0

    for start in range(0, len(rows), args.batch_size):
        batch = rows[start : start + args.batch_size]
        texts = [r["content_in_text"][:8000] for r in batch]
        try:
            vectors = await embed_texts(texts)
        except Exception as e:  # noqa: BLE001
            print(f"Batch {start // args.batch_size} failed: {e}")
            failed += len(batch)
            continue

        async with pool.acquire() as conn:
            for row, vec in zip(batch, vectors):
                await conn.execute(
                    "UPDATE kb_pages SET embedding = $1::vector WHERE id = $2",
                    _embedding_to_text(vec),
                    row["id"],
                )
        done += len(batch)
        print(f"Backfilled {done}/{len(rows)} (dim={dim})")

    await pool.close()
    print(f"Done. {done} embedded, {failed} failed.")


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
