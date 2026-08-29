"""Knowledge Base models and data structures."""

from typing import Any, Dict, List, Optional
from models.base import BaseSchema


class KBPage(BaseSchema):
    """A single page/chunk inside a Knowledge Base collection."""

    id: Optional[int] = None
    kb_id: str
    title: str
    content: str
    tags: List[str] = []
    page_meta: Dict[str, Any] = {}
    created_at: Optional[str] = None


class KBSearchResult(BaseSchema):
    """Result of a KB search query."""

    title: str
    content: str
    tags: List[str] = []
    score: float = 0.0
    metadata: Dict[str, Any] = {}


class KBCollection(BaseSchema):
    """A collection/group of KB documents belonging to an organisation or topic."""

    id: Optional[int] = None
    org_id: str
    collection_name: str
    description: Optional[str] = None
    process_id: Optional[int] = None
    stage_id: Optional[int] = None
    created_at: Optional[str] = None
