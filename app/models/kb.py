"""Knowledge base models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class KnowledgePage(BaseModel):
    id: str
    kb_id: str
    title: str
    content: str
    source_type: str
    page_meta: dict[str, Any] = Field(default_factory=dict)
    content_in_text: str = ""
    created_at: Optional[datetime] = None
    similarity: float = 0.0


class IngestRequest(BaseModel):
    kb_id: str
    title: str = ""
    content: str = ""
    url: str = ""
    source_type: str = "text"
    document_id: str = ""
    tags: list[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    query: str
    kb_ids: list[str]
    top_k: int = 3
    tags: Optional[list[str]] = None


class SearchResult(BaseModel):
    results: list[KnowledgePage] = Field(default_factory=list)
    total: int = 0
