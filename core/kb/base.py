"""Knowledge Base abstract base class and core data structures."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Dict, Any


@dataclass
class KnowledgePage:
    """Represents a chunk/page of knowledge stored in Postgres."""

    id: int
    kb_id: str
    title: str
    content: str
    source_type: str
    page_meta: dict
    content_in_text: str
    created_at: str
    similarity: float = 0.0


def embedding_to_text(vec: list[float]) -> str:
    """Format float array into Postgres vector literal '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def blend_results(
    vector_pages: list[KnowledgePage],
    fts_pages: list[KnowledgePage],
    top_k: int = 3,
    alpha: float = 0.5,
) -> list[KnowledgePage]:
    """Reciprocal Rank Fusion (RRF) blending vector search + FTS results."""
    rrf_k = 60
    scores: dict[int, float] = {}
    page_by_id: dict[int, KnowledgePage] = {}

    for rank, page in enumerate(vector_pages):
        scores[page.id] = scores.get(page.id, 0.0) + (1.0 - alpha) * (1.0 / (rrf_k + rank + 1))
        page_by_id[page.id] = page

    for rank, page in enumerate(fts_pages):
        scores[page.id] = scores.get(page.id, 0.0) + alpha * (1.0 / (rrf_k + rank + 1))
        page_by_id[page.id] = page

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    out: list[KnowledgePage] = []
    for pid, rrf_score in ranked[:top_k]:
        p = page_by_id[pid]
        p.similarity = rrf_score
        out.append(p)
    return out


class KnowledgeBase(ABC):
    """Abstract interface for multi-KB retrieval systems."""

    @abstractmethod
    async def search(
        self,
        kb_ids: list[str],
        query: str,
        top_k: int = 3,
        tags: Optional[list[str]] = None,
    ) -> list[KnowledgePage]:
        pass

    @abstractmethod
    async def add_page(
        self,
        kb_id: str,
        title: str,
        content: str,
        source_type: str = "text",
        page_meta: Optional[dict] = None,
        embedding: Optional[list[float]] = None,
    ) -> int:
        pass

    @abstractmethod
    async def list_available(
        self, kb_ids: list[str], top_k: int = 10
    ) -> list[KnowledgePage]:
        pass

    @abstractmethod
    async def delete_page(self, page_id: int) -> bool:
        pass

    @abstractmethod
    async def delete_document(self, kb_id: str, title: str) -> int:
        pass
