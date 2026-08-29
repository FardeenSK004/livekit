"""Knowledge Base data models."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class KBPage(BaseModel):
    """A single page/chunk inside a Knowledge Base collection."""

    id: Optional[int] = None
    kb_id: str
    title: str
    content: str
    tags: List[str] = []
    page_meta: Dict[str, Any] = {}
    created_at: Optional[str] = None


class KBSearchResult(BaseModel):
    """Result of a KB search query."""

    title: str
    content: str
    tags: List[str] = []
    score: float = 0.0
    metadata: Dict[str, Any] = {}
