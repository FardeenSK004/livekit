"""Appointment metadata models."""

from typing import Optional
from pydantic import BaseModel, Field


class AppointmentMetadata(BaseModel):
    """Structured appointment metadata extracted from call conversation."""

    provider_user_id: Optional[int] = Field(
        default=None, description="Doctor/Provider user ID"
    )
    provider_name: Optional[str] = Field(
        default=None, description="Doctor/Provider name"
    )
    preferred_datetime: Optional[str] = Field(
        default=None,
        description="ISO 8601 UTC appointment timestamp (YYYY-MM-DDTHH:MM:SSZ)",
    )
    appointment_title: Optional[str] = Field(
        default=None, description="Appointment consultation title or reason"
    )
    appointment_notes: Optional[str] = Field(
        default=None, description="Additional notes or symptoms provided by caller"
    )
