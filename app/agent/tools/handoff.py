"""transfer_to_human tool implementation."""

from __future__ import annotations

import logging

from app.agent.handoff import (
    dial_human_via_sip,
    enforce_silence_on_handoff,
    notify_handoff_webhook,
    resolve_transfer_target,
)

logger = logging.getLogger("app.agent.tools.handoff")


async def execute_handoff(
    *,
    reason: str,
    department: str,
    room_name: str,
    job_metadata: str,
    agent,
    session,
    transfer_numbers: dict | None = None,
) -> str:
    logger.info("Handoff requested. Reason: %s, Department: %s", reason, department)

    target_number, trunk_id = resolve_transfer_target(
        department, job_metadata, transfer_numbers
    )

    try:
        import json

        payload = json.loads(job_metadata) if job_metadata else {}
    except Exception:
        payload = {}

    call_id = payload.get("call_id") or payload.get("voice_id") or room_name

    await dial_human_via_sip(
        room_name=room_name,
        target_number=target_number,
        trunk_id=trunk_id,
        department=department,
        call_id=str(call_id),
    )
    await notify_handoff_webhook(
        room_name=room_name,
        reason=reason,
        department=department,
        job_metadata=job_metadata,
    )
    await enforce_silence_on_handoff(agent, session)

    return "TRANSFER_COMPLETE. Do not speak."
