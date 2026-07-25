"""Call dispatcher — handles dispatch of a single call."""

from __future__ import annotations

import logging
import traceback

from app.services.livekit import livekit_service

logger = logging.getLogger("app.dispatcher.worker")


async def dispatch_call(payload: dict) -> bool:
    """Dispatch a single call to LiveKit. Returns True on success."""
    call_id = payload.get("call_id") or payload.get("voice_id")
    room_name = payload.get("_resolved_room_name", f"call_{call_id}")
    phone_number = payload.get("_resolved_phone_number")
    trunk_id = payload.get("_resolved_trunk_id")
    sip_number = payload.get("_resolved_sip_number")

    if not phone_number:
        logger.error("No phone number for call %s", call_id)
        return False

    try:
        logger.info("[Call %s] Creating agent dispatch for room %s", call_id, room_name)
        dispatch = await livekit_service.create_agent_dispatch(room_name, payload)
        logger.info("[Call %s] Dispatch created: %s", call_id, dispatch.id)
    except Exception as e:
        logger.error(
            "[Call %s] Agent dispatch failed: %s\n%s",
            call_id,
            e,
            traceback.format_exc(),
        )
        return False

    try:
        logger.info(
            "[Call %s] Initiating SIP call to %s via trunk %s",
            call_id,
            phone_number,
            trunk_id,
        )
        sip_part = await livekit_service.create_sip_participant(
            room_name=room_name,
            sip_trunk_id=trunk_id,
            sip_call_to=phone_number,
            sip_number=sip_number,
            participant_identity=f"sip_{call_id}",
            participant_name="Mantra Voice",
            play_ringtone=False,
            wait_until_answered=True,
            play_dialtone=False,
        )
        logger.info(
            "[Call %s] SIP Participant created: %s",
            call_id,
            sip_part.participant_identity,
        )
        return True
    except Exception as e:
        logger.error(
            "[Call %s] SIP Call trigger failed: %s\n%s",
            call_id,
            e,
            traceback.format_exc(),
        )
        try:
            await livekit_service.delete_room(room_name)
        except Exception:
            pass
        return False
