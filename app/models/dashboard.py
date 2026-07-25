"""Dashboard and metrics models."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class MetricsResponse(BaseModel):
    today_total_calls: int = 0
    answer_rate: float = 0.0
    avg_duration_seconds: float = 0.0


class ActiveCall(BaseModel):
    call_id: str
    room_name: str
    status: str
    started_at: Optional[str] = None
    duration_seconds: int = 0


class StreamEvent(BaseModel):
    pending_calls: int = 0
    active_calls: int = 0
    max_concurrency: int = 0
    active_call_details: list[ActiveCall] = Field(default_factory=list)
    timestamp: str = ""


class CallHistoryEntry(BaseModel):
    call_id: str
    status: str
    caller: str = ""
    duration_seconds: int = 0
    timestamp: str = ""
    recording_url: str = ""


class PaginatedResponse(BaseModel):
    items: list[Any] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
