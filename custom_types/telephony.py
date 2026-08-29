"""Telephony type definitions and request schemas."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class OutboundCallPayload(BaseModel):
    phone: Optional[str] = None
    client_phone: Optional[str] = None
    call_from: Optional[str] = None
    call_id: Optional[str] = None
    voice_id: Optional[str] = None
    event_id: Optional[str] = None
    org_id: Optional[str] = None
    kb_id: Optional[str] = None
    kb_tags: Optional[List[str]] = None
    prompt: Optional[str] = None
    voice: Optional[str] = None
    model: Optional[str] = None
    process_id: Optional[int] = None
    stage_id: Optional[int] = None
    client_name: Optional[str] = None
    appointment_data: Optional[Dict[str, Any]] = None
    stage_details: Optional[List[Dict[str, Any]]] = None
    process_stage_data: Optional[List[Dict[str, Any]]] = None
    transfer_numbers: Optional[Dict[str, str]] = None
    trunk_id: Optional[str] = None
    country_code: Optional[str] = None


class DispatchRuleRequest(BaseModel):
    name: str
    trunk_ids: List[str]
    rule_type: str = "individual"
    room_prefix: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
