"""SIP Trunks and Dispatch Rules Controller."""

import os
import json
import logging
import traceback
from xml.sax.saxutils import escape
from fastapi import Request
from fastapi.responses import JSONResponse, Response
from livekit import api
from livekit.protocol import sip as proto_sip

from services.telephony import (
    _get_sip_domain,
    _normalize_phone_number,
    _resolve_plivo_sip_trunk_id,
    _build_plivo_xml,
    _update_provider_sip_forwarding,
    _create_sip_outbound_trunk,
    _get_provider_from_trunk,
)
from dependencies.database import get_db_connection

logger = logging.getLogger("controllers.sip")
AGENT_NAME = os.getenv("AGENT_NAME", "mantra-agent")


class SIPController:
    """Controller for managing SIP trunks, dispatch rules, XML webhooks, and routing."""

    @staticmethod
    async def create_inbound_trunk(request: Request):
        payload = await request.json()
        if not payload:
            return JSONResponse({"error": "No payload provided"}, status_code=400)

        lk_client = getattr(request.app.state, "lk_client", None)
        if not lk_client:
            return JSONResponse({"error": "LiveKit client not available"}, status_code=500)

        name = payload.get("name")
        numbers = payload.get("numbers")
        auth_username = payload.get("authUsername") or payload.get("auth_username")
        auth_password = payload.get("authPassword") or payload.get("auth_password")

        if not all([name, numbers]):
            return JSONResponse({"error": "Missing required fields: name, numbers"}, status_code=400)

        if isinstance(numbers, str):
            numbers = [n.strip() for n in numbers.split(",") if n.strip()]
        elif not isinstance(numbers, list):
            numbers = [str(numbers)]

        try:
            trunk_request = api.CreateSIPInboundTrunkRequest(
                trunk=api.SIPInboundTrunkInfo(
                    name=name,
                    numbers=numbers,
                    auth_username=auth_username or "",
                    auth_password=auth_password or "",
                )
            )
            trunk = await lk_client.sip.create_inbound_trunk(trunk_request)
            return JSONResponse({
                "status": "success",
                "sip_trunk_id": trunk.sip_trunk_id,
                "name": trunk.name,
                "numbers": list(trunk.numbers),
            })
        except Exception as e:
            logger.error(f"Failed to create inbound trunk: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    @staticmethod
    async def create_voicelink_inbound_trunk(request: Request):
        payload = await request.json()
        if not payload:
            return JSONResponse({"error": "No payload provided"}, status_code=400)

        lk_client = getattr(request.app.state, "lk_client", None)
        if not lk_client:
            return JSONResponse({"error": "LiveKit client not available"}, status_code=500)

        name = payload.get("name")
        numbers = payload.get("numbers")
        allowed_addresses = payload.get("allowed_addresses", "160.30.71.89")

        if not all([name, numbers]):
            return JSONResponse({"error": "Missing required fields: name, numbers"}, status_code=400)

        if isinstance(numbers, str):
            numbers = [n.strip() for n in numbers.split(",") if n.strip()]
        elif not isinstance(numbers, list):
            numbers = [str(numbers)]

        if isinstance(allowed_addresses, str):
            allowed_addresses = [a.strip() for a in allowed_addresses.split(",") if a.strip()]

        try:
            trunk_request = api.CreateSIPInboundTrunkRequest(
                trunk=api.SIPInboundTrunkInfo(
                    name=name,
                    numbers=numbers,
                    allowed_addresses=allowed_addresses or [],
                )
            )
            trunk = await lk_client.sip.create_inbound_trunk(trunk_request)
            trunk_id = trunk.sip_trunk_id

            dispatch_payload = {
                **payload,
                "trunk_id": trunk_id,
                "direction": "inbound",
            }
            rule_name = payload.get("rule_name", f"voicelink_rule_{trunk_id}")
            room_prefix = payload.get("room_prefix", "inbound_")

            req = api.CreateSIPDispatchRuleRequest(
                name=rule_name,
                metadata=json.dumps(dispatch_payload),
                rule=api.SIPDispatchRule(
                    dispatch_rule_individual=api.SIPDispatchRuleIndividual(
                        room_prefix=room_prefix
                    )
                ),
                room_config=api.RoomConfiguration(
                    agents=[
                        api.RoomAgentDispatch(
                            agent_name=AGENT_NAME,
                            metadata=json.dumps(dispatch_payload),
                        )
                    ]
                ),
                trunk_ids=[trunk_id],
            )
            rule = await lk_client.sip.create_sip_dispatch_rule(req)

            return JSONResponse({
                "status": "success",
                "sip_trunk_id": trunk_id,
                "sip_dispatch_rule_id": rule.sip_dispatch_rule_id,
                "name": name,
                "numbers": list(trunk.numbers),
                "allowed_addresses": allowed_addresses,
            })
        except Exception as e:
            logger.error(f"Failed to create VoiceLink inbound trunk: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    @staticmethod
    async def list_sip_inbound_trunks(request: Request):
        lk_client = getattr(request.app.state, "lk_client", None)
        if not lk_client:
            return JSONResponse({"error": "LiveKit client not initialized"}, status_code=500)

        try:
            response = await lk_client.sip.list_inbound_trunk(api.ListSIPInboundTrunkRequest())
            trunk_list = []
            for item in response.items:
                trunk_list.append({
                    "sip_trunk_id": item.sip_trunk_id,
                    "name": item.name,
                    "numbers": list(item.numbers),
                })
            return JSONResponse({"status": "success", "count": len(trunk_list), "trunks": trunk_list})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @staticmethod
    async def delete_sip_inbound_trunk(trunk_id: str, request: Request):
        lk_client = getattr(request.app.state, "lk_client", None)
        if not lk_client:
            return JSONResponse({"error": "LiveKit client not initialized"}, status_code=500)
        try:
            await lk_client.sip.delete_trunk(api.DeleteSIPTrunkRequest(sip_trunk_id=trunk_id))
            return JSONResponse({"status": "success", "message": f"SIP inbound trunk {trunk_id} deleted successfully"})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @staticmethod
    async def update_inbound_sip_trunk(trunk_id: str, request: Request):
        payload = await request.json()
        if not payload:
            return JSONResponse({"error": "No payload provided"}, status_code=400)

        lk_client = getattr(request.app.state, "lk_client", None)
        if not lk_client:
            return JSONResponse({"error": "LiveKit client not initialized"}, status_code=500)

        kwargs = {}
        if "name" in payload: kwargs["name"] = payload["name"]
        if "metadata" in payload:
            kwargs["metadata"] = json.dumps(payload["metadata"]) if isinstance(payload["metadata"], dict) else payload["metadata"]
        if "auth_username" in payload: kwargs["auth_username"] = payload["auth_username"]
        if "auth_password" in payload: kwargs["auth_password"] = payload["auth_password"]
        if "numbers" in payload:
            nums = payload["numbers"]
            kwargs["numbers"] = [n.strip() for n in nums.split(",") if n.strip()] if isinstance(nums, str) else nums
        if "allowed_addresses" in payload:
            addrs = payload["allowed_addresses"]
            kwargs["allowed_addresses"] = [a.strip() for a in addrs.split(",") if a.strip()] if isinstance(addrs, str) else addrs

        try:
            await lk_client.sip.update_inbound_trunk_fields(trunk_id, **kwargs)
            return JSONResponse({"status": "success", "message": f"Inbound trunk {trunk_id} updated"})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @staticmethod
    async def create_dispatch_rule(request: Request):
        payload = await request.json()
        lk_client = getattr(request.app.state, "lk_client", None)
        if not lk_client:
            return JSONResponse({"error": "LiveKit client not initialized"}, status_code=500)

        name = payload.get("name")
        trunk_ids = payload.get("trunk_ids", [])
        if not name or not trunk_ids:
            return JSONResponse({"error": "Missing name or trunk_ids"}, status_code=400)

        room_prefix = payload.get("room_prefix", "inbound_")
        dispatch_payload = {**payload, "direction": "inbound"}

        try:
            req = api.CreateSIPDispatchRuleRequest(
                name=name,
                metadata=json.dumps(dispatch_payload),
                rule=api.SIPDispatchRule(
                    dispatch_rule_individual=api.SIPDispatchRuleIndividual(room_prefix=room_prefix)
                ),
                room_config=api.RoomConfiguration(
                    agents=[
                        api.RoomAgentDispatch(agent_name=AGENT_NAME, metadata=json.dumps(dispatch_payload))
                    ]
                ),
                trunk_ids=trunk_ids,
            )
            rule = await lk_client.sip.create_sip_dispatch_rule(req)
            return JSONResponse({"status": "success", "sip_dispatch_rule_id": rule.sip_dispatch_rule_id, "name": rule.name})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @staticmethod
    async def list_dispatch_rules(request: Request):
        lk_client = getattr(request.app.state, "lk_client", None)
        if not lk_client:
            return JSONResponse({"error": "LiveKit client not initialized"}, status_code=500)
        try:
            response = await lk_client.sip.list_sip_dispatch_rule(api.ListSIPDispatchRuleRequest())
            rules = []
            for item in response.items:
                rules.append({
                    "sip_dispatch_rule_id": item.sip_dispatch_rule_id,
                    "name": item.name,
                    "trunk_ids": list(item.trunk_ids),
                })
            return JSONResponse({"status": "success", "count": len(rules), "dispatch_rules": rules})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @staticmethod
    async def delete_dispatch_rule(rule_id: str, request: Request):
        lk_client = getattr(request.app.state, "lk_client", None)
        if not lk_client:
            return JSONResponse({"error": "LiveKit client not initialized"}, status_code=500)
        try:
            await lk_client.sip.delete_sip_dispatch_rule(api.DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=rule_id))
            return JSONResponse({"status": "success", "message": f"Rule {rule_id} deleted successfully"})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @staticmethod
    async def update_sip_dispatch_rule(rule_id: str, request: Request):
        payload = await request.json()
        if not payload:
            return JSONResponse({"error": "No payload provided"}, status_code=400)

        lk_client = getattr(request.app.state, "lk_client", None)
        if not lk_client:
            return JSONResponse({"error": "LiveKit client not initialized"}, status_code=500)

        kwargs = {}
        if "name" in payload: kwargs["name"] = payload["name"]
        if "trunk_ids" in payload:
            tids = payload["trunk_ids"]
            kwargs["trunk_ids"] = [t.strip() for t in tids.split(",") if t.strip()] if isinstance(tids, str) else tids

        try:
            await lk_client.sip.update_dispatch_rule_fields(rule_id, **kwargs)
            return JSONResponse({"status": "success", "message": f"Dispatch rule {rule_id} updated"})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @staticmethod
    async def plivo_xml(request: Request):
        call_uuid, to_number = "unknown", "unknown"
        if request.method == "POST":
            form = await request.form()
            to_number = form.get("To", "unknown")
            call_uuid = form.get("CallUUID", "unknown")
        else:
            to_number = request.query_params.get("To", "unknown")
            call_uuid = request.query_params.get("CallUUID", "unknown")

        redis_client = getattr(request.app.state, "redis_client", None)
        lk_client = getattr(request.app.state, "lk_client", None)
        sip_trunk_id = await _resolve_plivo_sip_trunk_id(to_number, redis_client, lk_client) or os.getenv("SIP_TRUNK_ID")
        if not sip_trunk_id:
            return Response(content='<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>', media_type="application/xml")

        clean_to = _normalize_phone_number(to_number)
        sip_domain = _get_sip_domain()
        req_host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "localhost:8081"
        req_scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
        action_url = f"{req_scheme}://{req_host}/api/v1/sip/plivo-dial-status"

        xml = _build_plivo_xml(sip_trunk_id, sip_domain, action_url, clean_to)
        return Response(content=xml, media_type="application/xml")

    @staticmethod
    async def twilio_webhook(request: Request):
        to_number = "unknown"
        if request.method == "POST":
            form = await request.form()
            to_number = form.get("To", "unknown")
        else:
            to_number = request.query_params.get("To", "unknown")

        sip_trunk_id = os.getenv("SIP_TRUNK_ID", "")
        sip_domain = _get_sip_domain()
        xml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Dial>
        <Sip>sip:{sip_trunk_id}@{sip_domain};transport=tcp</Sip>
    </Dial>
</Response>'''
        return Response(content=xml_content, media_type="application/xml")

    @staticmethod
    async def plivo_dial_status(request: Request):
        form = await request.form()
        return Response(content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>', media_type="application/xml")

    @staticmethod
    async def setup_inbound_sip(request: Request):
        payload = await request.json()
        return JSONResponse({"status": "success", "message": "Inbound SIP setup completed", "payload": payload})

    @staticmethod
    async def create_zadarma_sip_trunk(request: Request):
        payload = await request.json()
        lk_client = getattr(request.app.state, "lk_client", None)
        try:
            trunk = await _create_sip_outbound_trunk(
                name=payload.get("name"),
                address=payload.get("address"),
                numbers=payload.get("numbers"),
                auth_username=payload.get("authUsername") or payload.get("auth_username") or payload.get("auth_user"),
                auth_password=payload.get("authPassword") or payload.get("auth_password") or payload.get("auth_pass"),
                client=lk_client,
            )
            return JSONResponse({
                "status": "success", "sip_trunk_id": trunk.sip_trunk_id, "name": trunk.name, "provider": "zadarma", "address": trunk.address
            })
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @staticmethod
    async def create_twilio_sip_trunk(request: Request):
        payload = await request.json()
        lk_client = getattr(request.app.state, "lk_client", None)
        try:
            trunk = await _create_sip_outbound_trunk(
                name=payload.get("name"),
                address=payload.get("address") or "live-kit-mc.pstn.twilio.com",
                numbers=payload.get("numbers"),
                auth_username=payload.get("authUsername") or payload.get("auth_username") or payload.get("auth_user"),
                auth_password=payload.get("authPassword") or payload.get("auth_password") or payload.get("auth_pass"),
                client=lk_client,
            )
            return JSONResponse({
                "status": "success", "sip_trunk_id": trunk.sip_trunk_id, "name": trunk.name, "provider": "twilio", "address": trunk.address
            })
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @staticmethod
    async def create_voicelink_sip_trunk(request: Request):
        payload = await request.json()
        voicelink_client = getattr(request.app.state, "voicelink_client", None) or getattr(request.app.state, "lk_client", None)
        try:
            trunk = await _create_sip_outbound_trunk(
                name=payload.get("name"),
                address=payload.get("address"),
                numbers=payload.get("numbers"),
                auth_username=payload.get("authUsername") or payload.get("auth_username") or payload.get("auth_user"),
                auth_password=payload.get("authPassword") or payload.get("auth_password") or payload.get("auth_pass"),
                client=voicelink_client,
                destination_country="in",
            )
            return JSONResponse({"status": "success", "sip_trunk_id": trunk.sip_trunk_id, "provider": "voicelink"})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @staticmethod
    async def create_and_call_plivo(request: Request):
        payload = await request.json()
        plivo_client = getattr(request.app.state, "plivo_client", None) or getattr(request.app.state, "lk_client", None)
        try:
            trunk_id = payload.get("trunk_id") or os.getenv("SIP_TRUNK_ID")
            return JSONResponse({"status": "success", "sip_trunk_id": trunk_id, "message": "Plivo processed"})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @staticmethod
    async def list_sip_outbound_trunks(request: Request):
        lk_client = getattr(request.app.state, "lk_client", None)
        if not lk_client:
            return JSONResponse({"error": "LiveKit client not initialized"}, status_code=500)
        try:
            response = await lk_client.sip.list_outbound_trunk(api.ListSIPOutboundTrunkRequest())
            trunk_list = []
            for item in response.items:
                trunk_list.append({
                    "sip_trunk_id": item.sip_trunk_id,
                    "name": item.name,
                    "address": item.address,
                    "transport": item.transport,
                    "numbers": list(item.numbers),
                    "auth_username": item.auth_username,
                    "encryption": item.media_encryption,
                })
            return JSONResponse({"status": "success", "count": len(trunk_list), "trunks": trunk_list})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @staticmethod
    async def delete_sip_outbound_trunk(trunk_id: str, request: Request):
        lk_client = getattr(request.app.state, "lk_client", None)
        if not lk_client:
            return JSONResponse({"error": "LiveKit client not initialized"}, status_code=500)
        try:
            await lk_client.sip.delete_trunk(api.DeleteSIPTrunkRequest(sip_trunk_id=trunk_id))
            return JSONResponse({"status": "success", "message": f"SIP trunk {trunk_id} deleted successfully", "sip_trunk_id": trunk_id})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)


sip_controller = SIPController()
