"""
PostgreSQL Full-Text Search (tsvector) + pgvector Knowledge Base implementation.
"""

import json
import logging
from typing import Optional, List, Dict, Any
import asyncpg

from core.kb.base import KnowledgeBase, KnowledgePage, embedding_to_text, blend_results
from core.kb.queries import (
    build_search_query,
    build_loose_search_query,
    build_vector_search_query,
    build_tag_search_query,
    build_list_docs_query,
)
from core.kb.gemini_embeddings import embed_text, embed_texts, embedding_enabled
from core.kb.chunking import adaptive_chunk
from core.kb.extractors import extract_pdf_text, extract_url_text
from core.kb.ingestion import ingest_file, ingest_text, ingest_url

logger = logging.getLogger("core.kb.knowledge_base")


class PostgresKnowledgeBase(KnowledgeBase):
    """PostgreSQL pgvector + FTS implementation with multi-tenant isolation."""

    def __init__(self, dsn: str):
        self.dsn = dsn
        self._pool: Optional[asyncpg.Pool] = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self.dsn, min_size=2, max_size=10, timeout=5.0
            )
        return self._pool

    async def close(self):
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def add_page(
        self,
        kb_id: str,
        title: str,
        content: str,
        source_type: str = "text",
        page_meta: Optional[dict] = None,
        embedding: Optional[list[float]] = None,
    ) -> int:
        pool = await self._get_pool()
        meta = page_meta or {}
        if embedding is None and embedding_enabled():
            try:
                embedding = await embed_text(f"{title}\n{content}")
            except Exception as e:
                logger.warning(f"Failed to compute embedding during add_page: {e}")

        emb_val = embedding_to_text(embedding) if embedding else None
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO kb_pages (kb_id, title, content, source_type, page_meta, content_in_text, embedding)
                VALUES ($1, $2, $3, $4, $5::jsonb, $3, $6::vector)
                RETURNING id
                """,
                kb_id,
                title,
                content,
                source_type,
                json.dumps(meta),
                emb_val,
            )
            return row["id"]

    async def search(
        self,
        kb_ids: list[str],
        query: str,
        top_k: int = 3,
        tags: Optional[list[str]] = None,
    ) -> list[KnowledgePage]:
        pool = await self._get_pool()
        clean_kb_ids = [str(k) for k in kb_ids]
        clean_tags = [str(t) for t in tags] if tags else None

        # 1. Semantic (vector) search if embeddings enabled
        vector_pages: list[KnowledgePage] = []
        if embedding_enabled():
            try:
                q_emb = await embed_text(query)
                if q_emb:
                    emb_str = embedding_to_text(q_emb)
                    async with pool.acquire() as conn:
                        rows = await conn.fetch(
                            build_vector_search_query(),
                            clean_kb_ids,
                            emb_str,
                            top_k * 2,
                            clean_tags,
                        )
                        for r in rows:
                            vector_pages.append(
                                KnowledgePage(
                                    id=r["id"],
                                    kb_id=r["kb_id"],
                                    title=r["title"],
                                    content=r["content"],
                                    source_type=r["source_type"],
                                    page_meta=json.loads(r["page_meta"]) if isinstance(r["page_meta"], str) else (r["page_meta"] or {}),
                                    content_in_text=r["content_in_text"],
                                    created_at=str(r["created_at"]),
                                    similarity=float(r["similarity"] or 0.0),
                                )
                            )
            except Exception as e:
                logger.warning(f"Vector search failed, falling back to FTS: {e}")

        # 2. Strict FTS search
        fts_pages: list[KnowledgePage] = []
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    build_search_query(),
                    clean_kb_ids,
                    query,
                    top_k * 2,
                    clean_tags,
                )
                for r in rows:
                    fts_pages.append(
                        KnowledgePage(
                            id=r["id"],
                            kb_id=r["kb_id"],
                            title=r["title"],
                            content=r["content"],
                            source_type=r["source_type"],
                            page_meta=json.loads(r["page_meta"]) if isinstance(r["page_meta"], str) else (r["page_meta"] or {}),
                            content_in_text=r["content_in_text"],
                            created_at=str(r["created_at"]),
                            similarity=float(r["similarity"] or 0.0),
                        )
                    )
        except Exception as e:
            logger.warning(f"Strict FTS query failed: {e}")

        if vector_pages and fts_pages:
            return blend_results(vector_pages, fts_pages, top_k=top_k)
        if vector_pages:
            return vector_pages[:top_k]
        if fts_pages:
            return fts_pages[:top_k]

        # 3. Fallback: Loose FTS
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    build_loose_search_query(),
                    clean_kb_ids,
                    query,
                    top_k,
                    clean_tags,
                )
                loose_pages = []
                for r in rows:
                    loose_pages.append(
                        KnowledgePage(
                            id=r["id"],
                            kb_id=r["kb_id"],
                            title=r["title"],
                            content=r["content"],
                            source_type=r["source_type"],
                            page_meta=json.loads(r["page_meta"]) if isinstance(r["page_meta"], str) else (r["page_meta"] or {}),
                            content_in_text=r["content_in_text"],
                            created_at=str(r["created_at"]),
                            similarity=float(r["similarity"] or 0.0),
                        )
                    )
                if loose_pages:
                    return loose_pages
        except Exception as e:
            logger.warning(f"Loose FTS fallback failed: {e}")

        # 4. Fallback: Tag search
        if clean_tags:
            try:
                async with pool.acquire() as conn:
                    rows = await conn.fetch(
                        build_tag_search_query(),
                        clean_kb_ids,
                        clean_tags,
                        top_k,
                    )
                    tag_pages = []
                    for r in rows:
                        tag_pages.append(
                            KnowledgePage(
                                id=r["id"],
                                kb_id=r["kb_id"],
                                title=r["title"],
                                content=r["content"],
                                source_type=r["source_type"],
                                page_meta=json.loads(r["page_meta"]) if isinstance(r["page_meta"], str) else (r["page_meta"] or {}),
                                content_in_text=r["content_in_text"],
                                created_at=str(r["created_at"]),
                                similarity=1.0,
                            )
                        )
                    if tag_pages:
                        return tag_pages
            except Exception as e:
                logger.warning(f"Tag search fallback failed: {e}")

        return []

    async def list_available(
        self, kb_ids: list[str], top_k: int = 10
    ) -> list[KnowledgePage]:
        pool = await self._get_pool()
        clean_kb_ids = [str(k) for k in kb_ids]
        async with pool.acquire() as conn:
            rows = await conn.fetch(build_list_docs_query(), clean_kb_ids, top_k)
            pages = []
            for r in rows:
                pages.append(
                    KnowledgePage(
                        id=r["id"],
                        kb_id=r["kb_id"],
                        title=r["title"],
                        content=r["content"],
                        source_type=r["source_type"],
                        page_meta=json.loads(r["page_meta"]) if isinstance(r["page_meta"], str) else (r["page_meta"] or {}),
                        content_in_text=r["content_in_text"],
                        created_at=str(r["created_at"]),
                        similarity=0.0,
                    )
                )
            return pages

    async def delete_page(self, page_id: int) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            res = await conn.execute("DELETE FROM kb_pages WHERE id = $1", page_id)
            return res.endswith("1")

    async def delete_document(self, kb_id: str, title: str) -> int:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            res = await conn.execute(
                "DELETE FROM kb_pages WHERE kb_id = $1 AND title LIKE $2",
                kb_id,
                f"{title}%",
            )
            try:
                return int(res.split(" ")[-1])
            except Exception:
                return 0

    async def get_kb_ids_for_org(self, org_id: str | int) -> list[str]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id FROM kb_collections WHERE org_id = $1::text", str(org_id)
            )
            ids = [str(r["id"]) for r in rows]
            ids.append(str(org_id))
            return ids

    async def get_collection_details_for_org(self, org_id: str | int) -> Optional[dict]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT process_id, stage_id FROM kb_collections WHERE org_id = $1::text AND (process_id IS NOT NULL OR stage_id IS NOT NULL) LIMIT 1",
                str(org_id),
            )
            return dict(row) if row else None

    async def prefetch_org_pages(self, kb_ids: list[str]) -> list[KnowledgePage]:
        pool = await self._get_pool()
        clean_kb_ids = [str(k) for k in kb_ids]
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, kb_id, title, content, source_type, page_meta, content_in_text, created_at
                FROM kb_pages
                WHERE kb_id = ANY($1::text[])
                ORDER BY created_at DESC
                LIMIT 50
                """,
                clean_kb_ids,
            )
            pages = []
            for r in rows:
                pages.append(
                    KnowledgePage(
                        id=r["id"],
                        kb_id=r["kb_id"],
                        title=r["title"],
                        content=r["content"],
                        source_type=r["source_type"],
                        page_meta=json.loads(r["page_meta"]) if isinstance(r["page_meta"], str) else (r["page_meta"] or {}),
                        content_in_text=r["content_in_text"],
                        created_at=str(r["created_at"]),
                        similarity=0.0,
                    )
                )
            return pages

    async def backfill_embeddings(self, kb_id: Optional[str] = None, limit: int = 100) -> int:
        if not embedding_enabled():
            return 0
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if kb_id:
                rows = await conn.fetch(
                    "SELECT id, title, content_in_text FROM kb_pages WHERE kb_id = $1 AND embedding IS NULL LIMIT $2",
                    kb_id,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    "SELECT id, title, content_in_text FROM kb_pages WHERE embedding IS NULL LIMIT $1",
                    limit,
                )

            if not rows:
                return 0

            texts = [f"{r['title']}\n{r['content_in_text']}" for r in rows]
            embeddings = await embed_texts(texts)

            for r, emb in zip(rows, embeddings):
                emb_str = embedding_to_text(emb)
                await conn.execute(
                    "UPDATE kb_pages SET embedding = $1::vector WHERE id = $2",
                    emb_str,
                    r["id"],
                )
            return len(rows)


__all__ = [
    "PostgresKnowledgeBase",
    "KnowledgePage",
    "KnowledgeBase",
    "blend_results",
    "embedding_to_text",
    "adaptive_chunk",
    "extract_pdf_text",
    "extract_url_text",
    "ingest_file",
    "ingest_text",
    "ingest_url",
]
