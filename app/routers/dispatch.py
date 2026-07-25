"""Dispatch test endpoints."""

from __future__ import annotations

import json
import logging
import time
import traceback

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.services.livekit import livekit_service
from app.services.sip import build_e164_phone, sip_service

logger = logging.getLogger("app.routers.dispatch")

router = APIRouter(tags=["dispatch"])


@router.post("/dispatch-test")
async def dispatch_test(request: Request):
    payload = await request.json()
    if not payload:
        return JSONResponse({"error": "No payload provided"}, status_code=400)

    logger.info(
        "Manual dispatch request with payload: %s",
        json.dumps(payload, separators=(",", ":")),
    )

    call_id = payload.get("call_id") or int(time.time())
    room_name = f"test_{call_id}"

    try:
        dispatch = await livekit_service.create_agent_dispatch(room_name, payload)
        logger.info(
            "Successfully dispatched agent to room %s, dispatch_id: %s",
            room_name,
            dispatch.id,
        )
    except Exception as e:
        logger.error("Dispatch failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)

    token = livekit_service.create_access_token("Tester", "Manual Tester", room_name)
    return JSONResponse(
        {
            "status": "success",
            "room": room_name,
            "token": token,
            "url": settings.LIVEKIT_URL,
        }
    )


@router.post("/api/v1/test/inbound-call")
async def test_inbound_call(request: Request):
    payload = await request.json()
    if not payload:
        return JSONResponse({"error": "No payload provided"}, status_code=400)

    logger.info("Test inbound call request: %s", json.dumps(payload, indent=2))

    call_id = int(time.time())
    room_name = f"test_inbound_{call_id}"
    payload["direction"] = "inbound"
    payload["call_id"] = call_id
    if "phone" in payload and "phone_number" not in payload:
        payload["phone_number"] = payload["phone"]

    try:
        logger.info("Dispatching agent to room %s", room_name)
        await livekit_service.create_agent_dispatch(room_name, payload)
    except Exception as e:
        logger.error("Agent dispatch failed: %s\n%s", e, traceback.format_exc())
        return JSONResponse(
            {"error": f"Agent dispatch failed: {str(e)}"}, status_code=500
        )

    try:
        trunk_id = payload.get("trunk_id")
        client_phone = payload.get("phone")
        phone_number = build_e164_phone(
            str(payload.get("country_code", "")),
            str(client_phone or ""),
        )
        if not trunk_id or not client_phone:
            return JSONResponse(
                {"error": "trunk_id and phone are required"}, status_code=400
            )

        logger.info("Initiating test SIP call to %s via trunk %s", phone_number, trunk_id)
        await livekit_service.create_sip_participant(
            room_name=room_name,
            sip_trunk_id=trunk_id,
            sip_call_to=phone_number,
            participant_identity=f"sip_test_{call_id}",
            participant_name="SIP Tester",
        )
    except Exception as e:
        logger.error("SIP Call trigger failed: %s\n%s", e, traceback.format_exc())
        return JSONResponse(
            {"error": f"SIP Call trigger failed: {str(e)}"}, status_code=500
        )

    return JSONResponse(
        {
            "status": "success",
            "message": "Test inbound call initiated",
            "room": room_name,
            "call_id": call_id,
        }
    )
