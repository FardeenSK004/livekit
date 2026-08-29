"""Webhook payload validation."""

from typing import Dict, Any


def validate_telephony_payload(payload: Dict[str, Any]) -> tuple[bool, str]:
    if not payload:
        return False, "Payload is empty"
    if not payload.get("client_phone") and not payload.get("phone"):
        return False, "Missing client_phone or phone"
    return True, ""
