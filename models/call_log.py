"""Call log database models and schemas."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from models.base import BaseSchema


class CallAttempt(BaseSchema):
    """Single call attempt entry within call log."""

    attempt_number: int = 1
    retry_count: int = 0
    attempted_at: str
    status: str
    ai_call_id: Optional[str] = None
    duration: int = 0
    recording_url: Optional[str] = None
    summary: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None


class CallLog(BaseSchema):
    """Call log record representing a phone call session."""

    call_id: str
    call_log: Optional[str] = None
    status: str
    recording_url: Optional[str] = None
    caller_number: Optional[str] = None
    called_number: Optional[str] = None
    trunk_id: Optional[str] = None
    attempts: List[CallAttempt] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
