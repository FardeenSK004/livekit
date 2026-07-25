"""Telephony webhook — outbound call dispatch."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import traceback

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.services.livekit import livekit_service
from app.services.redis import redis_service
from app.services.sip import build_e164_phone, sip_service

logger = logging.getLogger("app.routers.webhooks")

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


@router.post("/telephony")
async def handle_outbound_call_webhook(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON payload"}, status_code=400)
    if not payload:
        return JSONResponse({"error": "No payload provided"}, status_code=400)

    event_name = payload.get("event_name", "telephony_dispatch")
    logger.info(
        "Webhook received call request for event %s: %s",
        event_name,
        json.dumps(payload, separators=(",", ":")),
    )

    call_id = (
        payload.get("call_id")
        or payload.get("voice_id")
        or payload.get("event_id")
        or int(time.time())
    )
    room_name = f"call_{call_id}"

    phone_number = build_e164_phone(
        payload.get("client_country_code", ""),
        payload.get("client_phone", ""),
    )
    if not phone_number:
        return JSONResponse(
            {"error": "No client_phone provided in payload"}, status_code=400
        )

    trunk_id = (
        payload.get("trunk_id")
        or payload.get("call_from_id")
        or settings.SIP_TRUNK_ID
    )
    if not trunk_id:
        return JSONResponse({"error": "No SIP trunk ID configured"}, status_code=500)

    provider = await sip_service.get_provider_from_trunk(trunk_id)
    logger.info("Provider detected: %s", provider)

    try:
        logger.info("Step 1: Creating agent dispatch for room %s", room_name)
        dispatch = await livekit_service.create_agent_dispatch(room_name, payload)
        logger.info("Dispatch created: %s", dispatch.id)
    except Exception as e:
        logger.error("Agent dispatch failed: %s\n%s", e, traceback.format_exc())
        return JSONResponse(
            {"error": f"Agent dispatch failed: {str(e)}"}, status_code=500
        )

    async def trigger_sip():
        try:
            sip_number = payload.get("call_from")
            if sip_number and not str(sip_number).startswith("+"):
                sip_number = f"+{sip_number}"

            proxy_msg = "proxied Plivo client" if provider == "plivo" else "direct LiveKit client"
            logger.info(
                "Step 2: Initiating SIP call to %s via trunk %s using %s%s",
                phone_number,
                trunk_id,
                proxy_msg,
                f" (Caller ID: {sip_number})" if sip_number else "",
            )
            sip_part = await livekit_service.create_sip_participant(
                room_name=room_name,
                sip_trunk_id=trunk_id,
                sip_call_to=phone_number,
                sip_number=sip_number,
                participant_identity=f"sip_{call_id}",
                participant_name="SIP Caller",
                play_ringtone=False,
                wait_until_answered=True,
                provider=provider,
            )
            logger.info("SIP Participant created: %s", sip_part.participant_identity)
        except Exception as e:
            logger.error(
                "SIP Call trigger failed for %s: %s\n%s",
                room_name,
                e,
                traceback.format_exc(),
            )
            await sip_service.handle_sip_failure(call_id, room_name, e)

    asyncio.create_task(trigger_sip())

    token = livekit_service.create_access_token(
        f"monitor_{call_id}",
        "Call Monitor",
        room_name,
        can_publish=False,
        can_subscribe=True,
    )

    prompt = payload.get("prompt", "Voice interaction")
    return JSONResponse(
        {
            "status": "success",
            "message": f"Agent dispatched for {event_name}",
            "client_name": payload.get("client_name", "Unknown"),
            "purpose": prompt[:100] + ("..." if len(prompt) > 100 else ""),
            "room": room_name,
            "token": token,
            "url": settings.LIVEKIT_URL,
        }
    )
