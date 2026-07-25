"""Call-related models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class CallMetadata(BaseModel):
    prompt: str = ""
    client_name: str = ""
    call_id: str = ""
    lead_id: str = ""
    ai_payload: dict[str, Any] = Field(default_factory=dict)
    stage_id: int = 0
    stageDetails: list[dict[str, Any]] = Field(default_factory=list)
    client_custom_fields: dict[str, Any] = Field(default_factory=dict)
    client_phone: str = ""
    direction: str = "outbound"
    trunk_id: str = ""
    kb_id: str = ""
    kb_ids: list[str] = Field(default_factory=list)
    kb_tags: list[str] = Field(default_factory=list)
    org_id: str = ""
    process_id: str = ""
    transfer_numbers: dict[str, str] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class CallStatus(BaseModel):
    call_id: str
    status: str  # queued, ringing, active, completed, failed
    direction: str = "outbound"
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    sip_error: Optional[str] = None


class DispatchPayload(BaseModel):
    call_id: str
    phone_number: str
    trunk_id: str = ""
    metadata: CallMetadata = Field(default_factory=CallMetadata)
    room_name: str = ""
    sip_number: str = ""


class WebhookPayload(BaseModel):
    call_id: str = ""
    direction: str = "outbound"
    phone_number: str = ""
    metadata: CallMetadata = Field(default_factory=CallMetadata)

    model_config = {"extra": "ignore"}
