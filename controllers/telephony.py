"""Telephony controller for handling webhook dispatch and test calls."""

import os
import json
import time
import asyncio
import logging
from datetime import datetime
from fastapi import Request
from fastapi.responses import JSONResponse
from livekit import api

from helpers.database import save_call_event
from helpers.telemetry import report_telemetry
from services.telephony import _get_provider_from_trunk

logger = logging.getLogger("controllers.telephony")
AGENT_NAME = os.getenv("AGENT_NAME", "mantra-agent")


class TelephonyController:
    """Controller for call dispatching, webhook processing, and test calls."""

    @staticmethod
    async def handle_outbound_webhook(request: Request):
        payload = await request.json()
        if not payload:
            return JSONResponse({"error": "No payload provided"}, status_code=400)

        event_name = payload.get("event_name", "telephony_dispatch")
        logger.info(f"Webhook received call request for event {event_name}: {json.dumps(payload, separators=(',',':'))}")

        tos_task_id = payload.get("tos_task_id") or payload.get("metadata", {}).get("tos_task_id")
        call_id = payload.get("call_id") or payload.get("voice_id") or payload.get("event_id") or int(time.time())

        redis_client = getattr(request.app.state, "redis_client", None)
        lk_client = getattr(request.app.state, "lk_client", None)
        plivo_client = getattr(request.app.state, "plivo_client", None)
        voicelink_client = getattr(request.app.state, "voicelink_client", None)

        def _telemetry(message_suffix: str):
            if tos_task_id:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    report_telemetry(
                        tos_task_id=tos_task_id,
                        message=f"[UI Server] {message_suffix}",
                        call_id=str(call_id),
                    )
                )

        _telemetry("webhook_received")

        if redis_client:
            try:
                await redis_client.delete(f"backend_sent:{call_id}")
            except Exception:
                pass

            is_retry = bool(
                payload.get("is_retry")
                or payload.get("retry")
                or (payload.get("event") in ("CALL_RETRY", "call_retry"))
                or request.query_params.get("retry")
            )
            if is_retry:
                try:
                    await redis_client.delete(f"lock:call:{call_id}")
                except Exception:
                    pass

            lock_acquired = await redis_client.set(f"lock:call:{call_id}", "1", nx=True, ex=30)
            if not lock_acquired:
                logger.warning(f"Duplicate telephony webhook hit ignored for call_id: {call_id}")
                return JSONResponse({
                    "status": "ignored",
                    "message": f"Duplicate request for call_id {call_id} already in progress",
                    "room": f"call_{call_id}"
                }, status_code=200)

        country_code = payload.get("client_country_code", "").strip("+")
        client_phone = payload.get("client_phone", "").strip()

        if client_phone.startswith("+"):
            phone_number = client_phone
        elif country_code and client_phone:
            phone_number = f"+{country_code}{client_phone}"
        else:
            phone_number = client_phone

        if not phone_number:
            return JSONResponse({"error": "No client_phone provided in payload"}, status_code=400)

        trunk_id = payload.get("trunk_id") or payload.get("call_from_id") or os.getenv("SIP_TRUNK_ID")
        if not trunk_id:
            return JSONResponse({"error": "No SIP trunk ID configured"}, status_code=500)

        provider = await _get_provider_from_trunk(trunk_id)
        room_name = f"call_{trunk_id}_{call_id}"

        payload_meta = payload.get("metadata")
        if not isinstance(payload_meta, dict):
            payload_meta = {}
        payload_meta["call_initiated_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        payload_meta.setdefault("provider", provider)
        payload["metadata"] = payload_meta

        asyncio.create_task(save_call_event(
            call_id=str(call_id),
            event_type="webhook_received",
            event_source="ui_server",
            event_payload={k: v for k, v in payload.items() if k != "prompt"},
        ))

        # Check queue flag or direct dispatch
        use_queue = os.getenv("USE_DISPATCH_QUEUE", "0") == "1"
        if use_queue and redis_client:
            payload["_resolved_trunk_id"] = trunk_id
            payload["_resolved_room_name"] = room_name
            payload["_resolved_sip_number"] = phone_number
            priority = int(payload.get("priority", 0))
            await redis_client.zadd("queue:pending", {json.dumps(payload): priority})
            logger.info(f"Call {call_id} pushed to queue:pending with priority {priority}")
            return JSONResponse({
                "status": "queued",
                "message": "Call queued successfully",
                "call_id": call_id,
                "room": room_name,
            })

        # Direct dispatch
        client_to_use = lk_client
        if provider == "plivo" and plivo_client:
            client_to_use = plivo_client
        elif provider == "voice_link" and voicelink_client:
            client_to_use = voicelink_client

        if not client_to_use:
            return JSONResponse({"error": "LiveKit client not available"}, status_code=500)

        try:
            dispatch = await client_to_use.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    room=room_name, agent_name=AGENT_NAME, metadata=json.dumps(payload)
                )
            )
            sip_participant = await client_to_use.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    room_name=room_name,
                    sip_trunk_id=trunk_id,
                    sip_call_to=phone_number,
                    participant_identity=f"phone_{phone_number.replace('+', '')}",
                    participant_name="Caller",
                )
            )
            return JSONResponse({
                "status": "success",
                "message": "Outbound call dispatched successfully",
                "call_id": call_id,
                "room": room_name,
                "dispatch_id": dispatch.id,
                "sip_participant_id": sip_participant.participant_id,
            })
        except Exception as e:
            logger.error(f"Failed to dispatch call: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    @staticmethod
    async def dispatch_test(request: Request):
        payload = await request.json()
        phone_number = payload.get("phone")
        if not phone_number:
            return JSONResponse({"error": "Phone number is required"}, status_code=400)

        trunk_id = payload.get("trunk_id") or os.getenv("SIP_TRUNK_ID")
        lk_client = getattr(request.app.state, "lk_client", None)
        if not lk_client:
            return JSONResponse({"error": "LiveKit client not initialized"}, status_code=500)

        call_id = f"test_{int(time.time())}"
        room_name = f"call_{trunk_id}_{call_id}"

        try:
            dispatch = await lk_client.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    room=room_name, agent_name=AGENT_NAME, metadata=json.dumps(payload)
                )
            )
            sip_part = await lk_client.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    room_name=room_name,
                    sip_trunk_id=trunk_id,
                    sip_call_to=phone_number,
                    participant_identity=f"phone_{phone_number.replace('+', '')}",
                    participant_name="Caller",
                )
            )
            return JSONResponse({
                "status": "success",
                "call_id": call_id,
                "room": room_name,
                "dispatch_id": dispatch.id,
                "participant_id": sip_part.participant_id,
            })
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @staticmethod
    async def test_inbound_call(request: Request):
        payload = await request.json()
        lk_client = getattr(request.app.state, "lk_client", None)
        if not lk_client:
            return JSONResponse({"error": "LiveKit client not initialized"}, status_code=500)

        call_id = f"test_inbound_{int(time.time())}"
        room_name = f"inbound_{call_id}"

        try:
            payload["direction"] = "inbound"
            dispatch = await lk_client.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    room=room_name, agent_name=AGENT_NAME, metadata=json.dumps(payload)
                )
            )
            return JSONResponse({
                "status": "success",
                "message": "Test inbound call initiated",
                "room": room_name,
                "call_id": call_id,
                "dispatch_id": dispatch.id,
            })
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)


telephony_controller = TelephonyController()
