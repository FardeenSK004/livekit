"""Knowledge retriever with in-memory session cache."""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

from app.kb.engine import kb_engine

logger = logging.getLogger("app.kb.retriever")


class KnowledgeRetriever:
    def __init__(self):
        self.session_cache: dict[str, str] = {}

    async def retrieve(
        self,
        query: str,
        kb_ids: list[str],
        top_k: int = 3,
        tags: Optional[list[str]] = None,
    ) -> str:
        if not kb_ids:
            return "No Knowledge Base configured for this session."

        cache_key = self._make_cache_key(query, kb_ids, tags)
        if cache_key in self.session_cache:
            logger.info("Cache hit for: '%s'", query)
            return self.session_cache[cache_key]

        try:
            from app.services.db import db_service

            if db_service._pool is None:
                await db_service.start()

            results = await kb_engine.search(
                kb_ids=kb_ids,
                query=query,
                top_k=top_k,
                tags=tags,
            )
        except Exception as e:
            logger.error("Error during retrieval: %s", e)
            return "An error occurred while searching the knowledge base."

        if not results:
            formatted = (
                "No relevant information found in the knowledge base for this query."
            )
        else:
            formatted = "--- RELEVANT KNOWLEDGE BASE INFORMATION ---\n\n"
            for i, r in enumerate(results, 1):
                formatted += f"Source {i} [{r['title']}]:\n{r['content_in_text']}\n\n"

        self.session_cache[cache_key] = formatted
        return formatted

    def clear_cache(self):
        self.session_cache.clear()

    @staticmethod
    def _make_cache_key(
        query: str, kb_ids: list[str], tags: Optional[list[str]]
    ) -> str:
        raw = f"{query.strip().lower()}|{sorted(kb_ids)}|{sorted(tags or [])}"
        return hashlib.md5(raw.encode()).hexdigest()


kb_retriever = KnowledgeRetriever()
