"""Call state, payload, and data transfer objects."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from custom_types.appointment import AppointmentMetadata


class CallPayload(BaseModel):
    """Incoming telephony webhook payload."""

    call_id: Optional[str] = None
    client_phone: Optional[str] = None
    client_phone_number: Optional[str] = None
    phone_number: Optional[str] = None
    client_name: Optional[str] = None
    org_id: Optional[int] = None
    process_id: Optional[int] = None
    stage_id: Optional[int] = None
    custom_prompt: Optional[str] = None
    lead_id: Optional[str] = None
    trunk_id: Optional[str] = None
    direction: Optional[str] = "outbound"
    language: Optional[str] = "en"
    voice: Optional[str] = "arushi"
    voice_speed: Optional[float] = 1.0
    model: Optional[str] = "deepseek"
    appointment_data: Optional[Dict[str, Any]] = None
    kb_ids: Optional[List[str]] = None
    kb_tags: Optional[List[str]] = None
    process_stage_data: Optional[List[Dict[str, Any]]] = None
    stage_details: Optional[List[Dict[str, Any]]] = None


class CallAnalysisResult(BaseModel):
    """Output structure of post-call LLM analysis."""

    summary: str = Field(default="Call completed.")
    next_call_on: Optional[str] = None
    sentiment_score: Optional[float] = None
    doctor: Optional[str] = None
    hospital_location: Optional[str] = None
    appointment_date_time: Optional[str] = None
    new_stage_id: Optional[int] = None
    derived_process_id: Optional[int] = None
    user_intent: Optional[str] = None
    client_name: Optional[str] = None
    appointment_metadata: Optional[AppointmentMetadata] = None


class CallAttemptRecord(BaseModel):
    """History record of a single call attempt."""

    attempt_number: int
    attempted_at: str
    status: str
    ai_job_id: Optional[str] = None
    duration_seconds: Optional[float] = 0.0
    summary: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
