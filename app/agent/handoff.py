"""Human handoff orchestration — SIP dial-out, webhook, silence enforcement."""

from __future__ import annotations

import datetime
import json
import logging
import os
from typing import Any, Optional

from livekit import api
from livekit.agents import Agent, AgentSession

from app.config import settings
from app.services.webhook import webhook_service

logger = logging.getLogger("app.agent.handoff")

SILENCE_INSTRUCTIONS = (
    "You are SILENT. The call has been transferred to a human agent. "
    "Say absolutely nothing. Do not speak, do not acknowledge, do not say goodbye. "
    "The human agent handles everything from here. SILENT."
)


async def dial_human_via_sip(
    *,
    room_name: str,
    target_number: str,
    trunk_id: str,
    department: str,
    call_id: str,
) -> bool:
    """Add a human agent to the room via SIP."""
    if not target_number or not trunk_id:
        missing = []
        if not target_number:
            missing.append("target phone number")
        if not trunk_id:
            missing.append("SIP trunk ID")
        logger.warning(
            "Cannot transfer: missing %s. Backend notification sent anyway.",
            ", ".join(missing),
        )
        return False

    try:
        lk_api = api.LiveKitAPI(
            url=os.getenv("LIVEKIT_URL"),
            api_key=os.getenv("LIVEKIT_API_KEY"),
            api_secret=os.getenv("LIVEKIT_API_SECRET"),
        )
        timestamp = datetime.datetime.now().strftime("%H%M%S%f")
        human_identity = f"human_{call_id}_{timestamp}"
        await lk_api.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                sip_trunk_id=trunk_id,
                sip_call_to=target_number,
                room_name=room_name,
                participant_identity=human_identity,
                participant_name=f"Human - {department.title()}",
            )
        )
        await lk_api.aclose()
        logger.info(
            "Human agent (%s) added to room %s for %s department",
            target_number,
            room_name,
            department,
        )
        return True
    except Exception as e:
        logger.error("Failed to add human agent via SIP: %s", e)
        return False


async def notify_handoff_webhook(
    *,
    room_name: str,
    reason: str,
    department: str,
    job_metadata: str,
) -> None:
    """Notify MantraAssist backend of a handoff request."""
    if not settings.MANTRAASSIST_BACKEND_URL:
        return

    try:
        payload = json.loads(job_metadata) if job_metadata else {}
    except Exception:
        payload = {}

    webhook_payload = {
        "event": "HANDOFF_REQUESTED",
        "data": {
            "room_name": room_name,
            "reason": reason,
            "department": department,
            "call_id": payload.get("call_id") or payload.get("voice_id"),
            "lead_id": payload.get("lead_id"),
            "client_name": payload.get("client_name", "User"),
        },
    }
    await webhook_service.send(webhook_payload)


async def enforce_silence_on_handoff(
    agent: Optional[Agent],
    session: Optional[AgentSession],
) -> None:
    """Override instructions and interrupt agent speech after handoff."""
    if agent:
        try:
            await agent.update_instructions(SILENCE_INSTRUCTIONS)
            logger.info("Agent instructions overridden to enforce silence")
        except Exception as e:
            logger.error("Failed to update agent instructions: %s", e)

    try:
        if agent and agent._session:
            agent._session.interrupt()
            logger.info("Agent speech interrupted for handoff")
    except Exception as e:
        logger.debug("Agent interrupt unavailable (non-fatal): %s", e)


def resolve_transfer_target(
    department: str,
    job_metadata: str,
    transfer_numbers: Optional[dict[str, str]] = None,
) -> tuple[str, str]:
    """Return (target_number, trunk_id) for a department transfer."""
    dept_lower = (department or "general").lower().strip()
    numbers = transfer_numbers or settings.transfer_numbers_map
    target_number = numbers.get(dept_lower, settings.TRANSFER_DEFAULT_NUMBER)

    try:
        payload = json.loads(job_metadata) if job_metadata else {}
    except Exception:
        payload = {}

    trunk_id = (
        settings.TRANSFER_SIP_TRUNK_ID
        or payload.get("trunk_id")
        or payload.get("call_from_id")
        or ""
    )
    return target_number, trunk_id
