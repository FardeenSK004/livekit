"""search_knowledge_base tool implementation."""

from __future__ import annotations

import logging
from typing import Optional

from app.kb.retriever import KnowledgeRetriever

logger = logging.getLogger("app.agent.tools.search_kb")


async def execute_search(
    query: str,
    *,
    kb_ids: list[str],
    kb_tags: list[str],
    specific_tag: Optional[str],
    retriever: KnowledgeRetriever,
) -> str:
    tags_to_search = [specific_tag] if specific_tag else kb_tags
    logger.info(
        "Agent requested knowledge base search for: '%s' with tags %s",
        query,
        tags_to_search,
    )
    return await retriever.retrieve(
        query,
        kb_ids=kb_ids,
        tags=tags_to_search if tags_to_search else None,
    )
