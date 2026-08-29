"""Call lifecycle audit event models."""

from typing import Any, Dict, Optional
from models.base import BaseSchema


class CallEvent(BaseSchema):
    """Lifecycle audit event for calls."""

    call_id: str
    event_type: str
    event_source: str
    event_payload: Dict[str, Any]
    event_log: Optional[str] = None
    event_status: str = "success"
    event_error: Optional[str] = None
    ai_call_id: Optional[str] = None
    created_at: Optional[str] = None
