"""SIP trunk and provider webhook routers."""

from __future__ import annotations

import json
import logging
import traceback

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from livekit import api

from app.config import settings
from app.services.inbound_setup import setup_inbound_sip_process
from app.services.livekit import livekit_service
from app.services.redis import redis_service
from app.services.sip import normalize_numbers, sip_service
from app.services.sip_providers import (
    build_plivo_xml,
    build_twilio_xml,
    normalize_phone_number,
    resolve_plivo_sip_trunk_id,
    resolve_twilio_sip_trunk_id,
)

logger = logging.getLogger("app.routers.sip")

router = APIRouter(prefix="/api/v1/sip", tags=["sip"])


@router.post("/trunks/inbound")
async def create_inbound_trunk(request: Request):
    payload = await request.json()
    if not payload:
        return JSONResponse({"error": "No payload provided"}, status_code=400)

    logger.info("Creating SIP Inbound Trunk with payload: %s", json.dumps(payload, indent=2))
    name = payload.get("name")
    numbers = payload.get("numbers")
    auth_username = payload.get("authUsername") or payload.get("auth_username")
    auth_password = payload.get("authPassword") or payload.get("auth_password")

    if not all([name, numbers]):
        return JSONResponse(
            {"error": "Missing required fields: name, numbers"}, status_code=400
        )

    numbers = normalize_numbers(numbers)
    try:
        trunk = await livekit_service.create_inbound_trunk(
            name=name,
            numbers=numbers,
            auth_username=auth_username or "",
            auth_password=auth_password or "",
        )
        return JSONResponse(
            {
                "status": "success",
                "sip_trunk_id": trunk.sip_trunk_id,
                "name": trunk.name,
                "numbers": list(trunk.numbers),
            }
        )
    except Exception as e:
        logger.error("Failed to create inbound trunk: %s\n%s", e, traceback.format_exc())
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/trunks/inbound")
async def list_sip_inbound_trunks():
    try:
        response = await livekit_service.list_inbound_trunks()
        trunk_list = [
            {
                "sip_trunk_id": item.sip_trunk_id,
                "name": item.name,
                "numbers": list(item.numbers),
            }
            for item in response.items
        ]
        return JSONResponse({"status": "success", "count": len(trunk_list), "trunks": trunk_list})
    except Exception as e:
        logger.error("Failed to list SIP inbound trunks: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.delete("/trunks/inbound/{trunk_id}")
async def delete_sip_inbound_trunk(trunk_id: str):
    if not trunk_id:
        return JSONResponse(
            {"status_code": 400, "status": "error", "error": "Trunk ID is required"},
            status_code=400,
        )
    try:
        await livekit_service.delete_trunk(trunk_id)
        logger.info("Successfully deleted SIP Inbound Trunk: %s", trunk_id)
        return JSONResponse(
            {
                "status_code": 200,
                "status": "success",
                "message": f"SIP inbound trunk {trunk_id} deleted successfully",
            }
        )
    except Exception as e:
        logger.error("Failed to delete SIP inbound trunk %s: %s", trunk_id, e)
        return JSONResponse(
            {"status_code": 500, "status": "error", "error": str(e)}, status_code=500
        )


@router.patch("/trunks/inbound/{trunk_id}")
async def update_inbound_sip_trunk(trunk_id: str, request: Request):
    payload = await request.json()
    if not payload:
        return JSONResponse({"error": "No payload provided"}, status_code=400)
    try:
        await sip_service.update_inbound_trunk(trunk_id, payload)
        logger.info("Inbound trunk updated: %s", trunk_id)
        return JSONResponse(
            {
                "status": "success",
                "message": f"Inbound trunk {trunk_id} updated",
                "sip_trunk_id": trunk_id,
            }
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        logger.error("Failed to update inbound trunk %s: %s\n%s", trunk_id, e, traceback.format_exc())
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/dispatch-rules")
async def create_dispatch_rule(request: Request):
    payload = await request.json()
    if not payload:
        return JSONResponse({"error": "No payload provided"}, status_code=400)

    logger.info("Creating dispatch rule with payload: %s", json.dumps(payload, indent=2))
    trunk_id = payload.get("trunk_id")
    if not trunk_id:
        return JSONResponse({"error": "trunk_id is required"}, status_code=400)

    room_prefix = payload.get("room_prefix", "inbound_")
    name = payload.get("name", f"rule_{trunk_id}")
    payload["direction"] = "inbound"
    if "phone" in payload and "phone_number" not in payload:
        payload["phone_number"] = payload["phone"]

    try:
        room_config = api.RoomConfiguration(
            agents=[
                api.RoomAgentDispatch(
                    agent_name="mantra-agent",
                    metadata=json.dumps(payload),
                )
            ]
        )
        rule = await livekit_service.create_dispatch_rule(
            name=name,
            trunk_ids=[trunk_id],
            metadata=payload,
            room_prefix=room_prefix,
            room_config=room_config,
        )
        return JSONResponse(
            {
                "status": "success",
                "sip_dispatch_rule_id": rule.sip_dispatch_rule_id,
                "name": name,
                "trunk_ids": [trunk_id],
                "room_prefix": room_prefix,
            }
        )
    except Exception as e:
        logger.error("Failed to create dispatch rule: %s\n%s", e, traceback.format_exc())
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/dispatch-rules")
async def list_dispatch_rules():
    try:
        response = await livekit_service.list_dispatch_rules()
        rule_list = []
        for item in response.items:
            rule_info = {}
            if item.rule:
                if item.rule.dispatch_rule_individual:
                    rule_info = {
                        "type": "individual",
                        "room_prefix": item.rule.dispatch_rule_individual.room_prefix,
                    }
                elif item.rule.dispatch_rule_direct:
                    rule_info = {
                        "type": "direct",
                        "room_name": item.rule.dispatch_rule_direct.room_name,
                    }
                elif item.rule.dispatch_rule_caller:
                    rule_info = {
                        "type": "caller",
                        "room_prefix": item.rule.dispatch_rule_caller.room_prefix,
                        "workspace_uid": item.rule.dispatch_rule_caller.workspace_uid,
                    }
            rule_list.append(
                {
                    "sip_dispatch_rule_id": item.sip_dispatch_rule_id,
                    "name": item.name,
                    "trunk_ids": list(item.trunk_ids),
                    "rule": rule_info,
                    "metadata": item.metadata,
                }
            )
        return JSONResponse({"status": "success", "count": len(rule_list), "rules": rule_list})
    except Exception as e:
        logger.error("Failed to list dispatch rules: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.delete("/dispatch-rules/{rule_id}")
async def delete_dispatch_rule(rule_id: str):
    if not rule_id:
        return JSONResponse(
            {"status_code": 400, "status": "error", "error": "Rule ID is required"},
            status_code=400,
        )
    try:
        await livekit_service.delete_dispatch_rule(rule_id)
        logger.info("Successfully deleted SIP Dispatch Rule: %s", rule_id)
        return JSONResponse(
            {
                "status_code": 200,
                "status": "success",
                "message": f"SIP dispatch rule {rule_id} deleted successfully",
            }
        )
    except Exception as e:
        logger.error("Failed to delete dispatch rule %s: %s", rule_id, e)
        return JSONResponse(
            {"status_code": 500, "status": "error", "error": str(e)}, status_code=500
        )


@router.patch("/dispatch-rules/{rule_id}")
async def update_sip_dispatch_rule(rule_id: str, request: Request):
    payload = await request.json()
    if not payload:
        return JSONResponse({"error": "No payload provided"}, status_code=400)
    try:
        await sip_service.update_dispatch_rule(rule_id, payload)
        logger.info("Dispatch rule updated: %s", rule_id)
        return JSONResponse(
            {
                "status": "success",
                "message": f"Dispatch rule {rule_id} updated",
                "sip_dispatch_rule_id": rule_id,
            }
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        logger.error("Failed to update dispatch rule %s: %s\n%s", rule_id, e, traceback.format_exc())
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/plivo-xml")
@router.post("/plivo-xml")
async def plivo_xml(request: Request):
    logger.warning("plivo_xml endpoint called (DEPRECATED - migrating to Zentrunk)")
    if request.method == "POST":
        form_data = await request.form()
        call_uuid = form_data.get("CallUUID", "unknown")
        to_number = form_data.get("To", "unknown")
    else:
        call_uuid = request.query_params.get("CallUUID", "unknown")
        to_number = request.query_params.get("To", "unknown")

    sip_trunk_id = await resolve_plivo_sip_trunk_id(to_number)
    if not sip_trunk_id:
        sip_trunk_id = settings.SIP_TRUNK_ID
        if not sip_trunk_id:
            return Response(
                content='<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>',
                media_type="application/xml",
            )

    clean_to = normalize_phone_number(to_number) if to_number != "unknown" else ""
    sip_domain = livekit_service.get_sip_domain()
    req_host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "localhost:8082"
    req_scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    action_url = f"{req_scheme}://{req_host}/api/v1/sip/plivo-dial-status"
    xml_content = build_plivo_xml(sip_trunk_id, sip_domain, action_url, clean_to)
    logger.info("Returning Plivo XML for %s", call_uuid)
    return Response(content=xml_content, media_type="application/xml")


@router.get("/twilio-webhook")
@router.post("/twilio-webhook")
async def twilio_webhook(request: Request):
    if request.method == "POST":
        form_data = await request.form()
        to_number = form_data.get("To", "unknown")
    else:
        to_number = request.query_params.get("To", "unknown")

    sip_trunk_id = await resolve_twilio_sip_trunk_id(to_number)
    if not sip_trunk_id:
        sip_trunk_id = settings.SIP_TRUNK_ID
        if not sip_trunk_id:
            return Response(
                content='<?xml version="1.0" encoding="UTF-8"?><Response><Reject/></Response>',
                media_type="application/xml",
            )

    sip_domain = livekit_service.get_sip_domain()
    xml_content = build_twilio_xml(sip_trunk_id, sip_domain)
    return Response(content=xml_content, media_type="application/xml")


@router.post("/plivo-dial-status")
async def plivo_dial_status(request: Request):
    logger.warning("plivo_dial_status endpoint called (DEPRECATED - migrating to Zentrunk)")
    form_data = await request.form()
    logger.info("Received Plivo Dial Status callback: %s", dict(form_data))
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )


@router.post("/inbound/setup")
async def setup_inbound_sip(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = None

    if payload is not None:
        logger.info("=== [SIP INBOUND SETUP REQUEST] ===\nPayload: %s", json.dumps(payload, indent=2))
    else:
        logger.info("=== [SIP INBOUND SETUP REQUEST] ===\nInvalid/Empty JSON Payload")

    response = await setup_inbound_sip_process(payload)
    logger.info("=== [SIP INBOUND SETUP RESPONSE] ===\nStatus: %s", response.status_code)
    return response


@router.post("/trunks/outbound")
@router.post("/trunks/outbound/zadarma")
async def create_zadarma_sip_trunk(request: Request):
    payload = await request.json()
    if not payload:
        return JSONResponse({"error": "No payload provided"}, status_code=400)

    logger.info(
        "[POST /api/v1/sip/trunks/outbound] Payload received: %s",
        json.dumps(payload, separators=(",", ":")),
    )
    try:
        trunk = await sip_service.create_outbound_trunk(payload, provider="zadarma")
        return JSONResponse(
            {
                "status": "success",
                "sip_trunk_id": trunk.sip_trunk_id,
                "name": trunk.name,
                "provider": "zadarma",
                "address": trunk.address,
            }
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/trunks/outbound/twilio")
async def create_twilio_sip_trunk(request: Request):
    payload = await request.json()
    if not payload:
        return JSONResponse({"error": "No payload provided"}, status_code=400)

    logger.info(
        "[POST /api/v1/sip/trunks/outbound/twilio] Payload received: %s",
        json.dumps(payload, separators=(",", ":")),
    )
    if not payload.get("address"):
        payload["address"] = "live-kit-mc.pstn.twilio.com"
    try:
        trunk = await sip_service.create_outbound_trunk(payload, provider="twilio")
        return JSONResponse(
            {
                "status": "success",
                "sip_trunk_id": trunk.sip_trunk_id,
                "name": trunk.name,
                "provider": "twilio",
                "address": trunk.address,
            }
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/trunks/outbound/plivo")
async def create_and_call_plivo(request: Request):
    payload = await request.json()
    if not payload:
        return JSONResponse({"error": "No payload provided"}, status_code=400)

    if not settings.LIVEKIT_URL:
        return JSONResponse({"error": "Plivo client not available"}, status_code=503)

    try:
        trunk_data = payload.get("trunk")
        if trunk_data:
            trunk = await sip_service.create_outbound_trunk(
                trunk_data,
                provider="plivo",
                client=livekit_service.plivo,
                destination_country="in",
            )
            trunk_id = trunk.sip_trunk_id
        elif "numbers" in payload and (
            "authUsername" in payload
            or "auth_username" in payload
            or "auth_user" in payload
        ):
            trunk = await sip_service.create_outbound_trunk(
                payload,
                provider="plivo",
                client=livekit_service.plivo,
                destination_country="in",
            )
            trunk_id = trunk.sip_trunk_id
        else:
            trunk_id = (
                payload.get("trunk_id")
                or payload.get("call_from_id")
                or settings.SIP_TRUNK_ID
            )

        if not trunk_id:
            return JSONResponse({"error": "No trunk_id provided or configured"}, status_code=400)

        from app.services.sip import build_e164_phone
        import time

        client_phone = payload.get("client_phone")
        if client_phone is not None:
            client_phone = str(client_phone).strip()

        if not client_phone:
            return JSONResponse(
                {
                    "status": "success",
                    "sip_trunk_id": trunk_id,
                    "message": "Trunk provisioned successfully (no call initiated)",
                }
            )

        phone_number = build_e164_phone(
            str(payload.get("client_country_code") or ""),
            client_phone,
        )
        call_id = payload.get("call_id") or payload.get("voice_id") or int(time.time())
        room_name = f"call_{call_id}"

        if not await redis_service.acquire_lock(f"lock:call:{call_id}", ttl=600):
            logger.warning("Duplicate Plivo call request ignored for call_id: %s", call_id)
            return JSONResponse({
                "status": "ignored",
                "message": f"Duplicate request for call_id {call_id} already processing",
                "room": room_name,
            }, status_code=200)

        await livekit_service.create_agent_dispatch(room_name, payload)

        sip_number = payload.get("call_from")
        if sip_number and not str(sip_number).startswith("+"):
            sip_number = f"+{sip_number}"

        sip_part = await livekit_service.create_sip_participant(
            room_name=room_name,
            sip_trunk_id=trunk_id,
            sip_call_to=phone_number,
            sip_number=sip_number,
            participant_identity=f"sip_{call_id}",
            participant_name="Mantra Voice",
            play_ringtone=False,
            wait_until_answered=True,
            provider="plivo",
        )

        return JSONResponse(
            {
                "status": "success",
                "sip_trunk_id": trunk_id,
                "room": room_name,
                "participant": sip_part.participant_identity,
                "call_id": call_id,
            }
        )
    except Exception as e:
        logger.error("Plivo unified call failed: %s\n%s", e, traceback.format_exc())
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/trunks/outbound")
async def list_sip_outbound_trunks():
    try:
        response = await livekit_service.list_outbound_trunks()
        trunk_list = [
            {
                "sip_trunk_id": item.sip_trunk_id,
                "name": item.name,
                "address": item.address,
                "transport": item.transport,
                "numbers": list(item.numbers),
                "auth_username": item.auth_username,
                "encryption": item.media_encryption,
            }
            for item in response.items
        ]
        return JSONResponse({"status": "success", "count": len(trunk_list), "trunks": trunk_list})
    except Exception as e:
        logger.error("Failed to list SIP outbound trunks: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.delete("/trunks/outbound/{trunk_id}")
async def delete_sip_outbound_trunk(trunk_id: str):
    if not trunk_id:
        return JSONResponse({"error": "Trunk ID is required"}, status_code=400)
    try:
        await livekit_service.delete_trunk(trunk_id)
        logger.info("Successfully deleted SIP outbound trunk: %s", trunk_id)
        return JSONResponse(
            {
                "status": "success",
                "message": f"SIP trunk {trunk_id} deleted successfully",
                "sip_trunk_id": trunk_id,
            }
        )
    except Exception as e:
        logger.error("Failed to delete SIP outbound trunk %s: %s", trunk_id, e)
        return JSONResponse({"error": str(e)}, status_code=500)
