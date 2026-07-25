"""SIP trunk and telephony models."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SipProvider(str, Enum):
    TWILIO = "twilio"
    PLIVO = "plivo"
    ZADARMA = "zadarma"


class SipTrunkConfig(BaseModel):
    provider: SipProvider
    trunk_id: str = ""
    address: str = ""
    destination_country: str = "in"
    phone_number: str = ""


class SipParticipant(BaseModel):
    sip_trunk_id: str
    sip_number: str
    room_name: str
    participant_identity: str = ""


class SipError(str, Enum):
    NO_ANSWER = "No Answer"
    BUSY = "Busy"
    INCOMPLETE = "Incomplete"


SIP_ERROR_MAP: dict[str, SipError] = {
    "408": SipError.NO_ANSWER,
    "timeout": SipError.NO_ANSWER,
    "no answer": SipError.NO_ANSWER,
    "486": SipError.BUSY,
    "busy": SipError.BUSY,
    "decline": SipError.BUSY,
}
