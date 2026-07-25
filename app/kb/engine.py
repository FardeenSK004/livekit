"""Knowledge base engine — PostgreSQL FTS-based search and ingestion."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

from app.services.db import db_service

logger = logging.getLogger("app.kb.engine")


def build_search_query(use_generated_column: bool = True) -> str:
    vector_expr = (
        "text_search"
        if use_generated_column
        else "to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(content_in_text, ''))"
    )
    return f"""
        SELECT id, kb_id, title, content, source_type, page_meta, content_in_text, created_at,
               ts_rank({vector_expr}, websearch_to_tsquery('simple', $2)) as similarity
        FROM kb_pages
        WHERE kb_id = ANY($1::text[])
          AND {vector_expr} @@ websearch_to_tsquery('simple', $2)
          AND ($4::text[] IS NULL OR
              (jsonb_typeof(page_meta->'tags_name') = 'array' AND page_meta->'tags_name' ?| $4::text[]) OR
              (jsonb_typeof(page_meta->'tags_name') = 'string' AND page_meta->>'tags_name' = ANY($4::text[]))
          )
        ORDER BY similarity DESC
        LIMIT $3
    """


def _clean_val(val: Any) -> Any:
    if isinstance(val, str):
        return val.replace("\x00", "")
    if isinstance(val, dict):
        return {k: _clean_val(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_clean_val(v) for v in val]
    return val


class PostgresKnowledgeBase:
    def __init__(self):
        self._use_generated_text_search: Optional[bool] = None

    async def _supports_generated_text_search(self, conn) -> bool:
        if self._use_generated_text_search is not None:
            return self._use_generated_text_search
        row = await conn.fetchrow(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'kb_pages' AND column_name = 'text_search'
            ) AS has_column
            """
        )
        self._use_generated_text_search = bool(row["has_column"]) if row else False
        return self._use_generated_text_search

    async def search(
        self,
        kb_ids: list[str],
        query: str,
        top_k: int = 3,
        tags: Optional[list[str]] = None,
    ) -> list[dict]:
        async with db_service.pool.acquire() as conn:
            use_generated = await self._supports_generated_text_search(conn)
            rows = await conn.fetch(
                build_search_query(use_generated_column=use_generated),
                kb_ids,
                query,
                top_k,
                tags,
            )
            results = []
            for r in rows:
                page_meta = r["page_meta"]
                if isinstance(page_meta, str):
                    page_meta = json.loads(page_meta)
                results.append(
                    {
                        "id": str(r["id"]),
                        "kb_id": r["kb_id"],
                        "title": r["title"],
                        "content": r["content"],
                        "source_type": r["source_type"],
                        "page_meta": page_meta or {},
                        "content_in_text": r["content_in_text"],
                        "created_at": r["created_at"],
                        "similarity": float(r["similarity"] or 0),
                    }
                )
            return results

    async def add_page(
        self,
        kb_id: str,
        title: str,
        content: str,
        content_in_text: str,
        source_type: str,
        page_meta: Optional[dict] = None,
        page_id: Optional[str] = None,
    ) -> str:
        page_id = page_id or str(uuid.uuid4())
        kb_id = _clean_val(kb_id)
        title = _clean_val(title)
        content = _clean_val(content)
        content_in_text = _clean_val(content_in_text)
        source_type = _clean_val(source_type)
        page_meta = _clean_val(page_meta or {})

        query = """
        INSERT INTO kb_pages (id, kb_id, title, content, content_in_text, source_type, page_meta)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id
        """
        async with db_service.pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                uuid.UUID(page_id),
                kb_id,
                title,
                content,
                content_in_text,
                source_type,
                json.dumps(page_meta),
            )
            return str(row["id"])

    async def delete_by_document(self, kb_id: str, document_id: str) -> int:
        query = (
            "DELETE FROM kb_pages WHERE kb_id = $1 AND page_meta->>'document_id' = $2"
        )
        async with db_service.pool.acquire() as conn:
            result = await conn.execute(
                query, _clean_val(kb_id), _clean_val(document_id)
            )
            return int(result.split()[-1]) if result.startswith("DELETE") else 0

    async def delete_page(self, page_id: str) -> bool:
        query = "DELETE FROM kb_pages WHERE id = $1"
        async with db_service.pool.acquire() as conn:
            result = await conn.execute(query, uuid.UUID(page_id))
            return result == "DELETE 1"

    async def delete_by_kb(self, kb_id: str) -> int:
        query = "DELETE FROM kb_pages WHERE kb_id = $1"
        async with db_service.pool.acquire() as conn:
            result = await conn.execute(query, _clean_val(kb_id))
            return int(result.split()[-1]) if result.startswith("DELETE") else 0


kb_engine = PostgresKnowledgeBase()
