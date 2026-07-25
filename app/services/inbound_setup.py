"""End-to-end inbound SIP setup — ported from mantra/ui_server.py."""

from __future__ import annotations

import json
import logging
import traceback

from fastapi.responses import JSONResponse
from livekit import api

from app.services.livekit import livekit_service
from app.services.org_config import upsert_org_config
from app.services.redis import redis_service
from app.services.sip_providers import update_provider_sip_forwarding

logger = logging.getLogger("app.services.inbound_setup")


async def setup_inbound_sip_process(payload: dict | None) -> JSONResponse:
    if payload is None:
        return JSONResponse(
            {"status_code": 400, "status": "error", "error": "Invalid JSON"},
            status_code=400,
        )

    number = payload.get("number")
    if not number:
        return JSONResponse(
            {"status_code": 400, "status": "error", "error": "number is required"},
            status_code=400,
        )

    name = payload.get("name", f"Inbound {number}")
    prompt = payload.get("prompt", "You are a helpful voice assistant.")
    voice = payload.get("voice", "arushi")
    model = payload.get("model", "deepseek")
    provider = payload.get("provider", "zadarma").lower().strip()

    org_id = payload.get("org_id")
    if not org_id:
        return JSONResponse(
            {"status_code": 400, "status": "error", "error": "org_id is required"},
            status_code=400,
        )

    kb_tags = payload.get("kb_tags", [])
    transfer_numbers = payload.get("transfer_numbers", {})
    client_name = payload.get("client_name", "User")
    process_id = payload.get("process_id")
    clean_number = number.replace("+", "")

    logger.info(
        "Starting end-to-end SIP setup for number: %s, org_id: %s, provider: %s",
        number,
        org_id,
        provider,
    )

    try:
        existing_trunk_id = None
        existing_rule_id = None
        force_new = payload.get("force_new", False)

        if not force_new:
            existing_trunk_id = await livekit_service.find_inbound_trunk_for_number(number)
            if existing_trunk_id:
                logger.info("Found existing inbound trunk %s for number %s", existing_trunk_id, number)
                existing_rule_id = await livekit_service.find_dispatch_rule_for_trunk(
                    existing_trunk_id
                )
                if existing_rule_id:
                    logger.info(
                        "Found existing dispatch rule %s for trunk %s",
                        existing_rule_id,
                        existing_trunk_id,
                    )
        else:
            logger.info("force_new=true: Skipping existing trunk/rule checks for %s", number)

        if existing_trunk_id and existing_rule_id:
            return JSONResponse(
                {
                    "status_code": 409,
                    "status": "error",
                    "error": "number_already_configured",
                    "message": f"Phone number {number} is already configured",
                    "existing_trunk_id": existing_trunk_id,
                    "existing_dispatch_rule_id": existing_rule_id,
                },
                status_code=409,
            )

        if existing_trunk_id:
            trunk_id = existing_trunk_id
            logger.info("Reusing existing LiveKit SIP Inbound Trunk: %s", trunk_id)
        else:
            trunk = await livekit_service.create_inbound_trunk(
                name=name, numbers=[number, clean_number]
            )
            trunk_id = trunk.sip_trunk_id
            logger.info("Created LiveKit SIP Inbound Trunk: %s", trunk_id)

        if provider in ("plivo", "twilio"):
            try:
                await redis_service.set_provider_trunk_mapping(provider, number, trunk_id)
                await redis_service.set_provider_trunk_mapping(provider, clean_number, trunk_id)
                logger.info("Stored %s SIP trunk mapping: %s -> %s", provider, number, trunk_id)
            except Exception as e:
                logger.warning("Failed to store %s SIP trunk mapping in Redis: %s", provider, e)

        if existing_rule_id:
            rule_id = existing_rule_id
            logger.info("Reusing existing LiveKit SIP Dispatch Rule: %s", rule_id)
        else:
            room_prefix = f"inbound_{trunk_id[-6:]}"
            metadata_dict = {
                "direction": "inbound",
                "prompt": prompt,
                "voice": voice,
                "model": model,
                "phone_number": number,
                "provider": provider,
            }
            room_config = api.RoomConfiguration(
                empty_timeout=300,
                departure_timeout=60,
                agents=[
                    api.RoomAgentDispatch(
                        agent_name="mantra-agent",
                        metadata=json.dumps(metadata_dict),
                    )
                ],
            )
            rule = await livekit_service.create_dispatch_rule(
                name=f"Rule for {name}",
                trunk_ids=[trunk_id],
                metadata=metadata_dict,
                room_prefix=room_prefix,
                room_config=room_config,
            )
            rule_id = rule.sip_dispatch_rule_id
            logger.info("Created LiveKit SIP Dispatch Rule: %s", rule_id)

        org_config_id = await upsert_org_config(
            org_id=str(org_id),
            phone_number=number,
            name=name,
            prompt=prompt,
            voice=voice,
            model=model,
            kb_tags=kb_tags,
            transfer_numbers=transfer_numbers,
            client_name=client_name,
            process_id=process_id,
            sip_trunk_id=trunk_id,
            dispatch_rule_id=rule_id,
        )

        sip_domain = livekit_service.get_sip_domain()
        sip_uri = f"sip:{clean_number}@{sip_domain}"

        logger.info("Updating %s SIP ID for %s to %s", provider, number, sip_uri)
        try:
            provider_response = await update_provider_sip_forwarding(provider, number, sip_uri)
        except Exception as e:
            return JSONResponse(
                {
                    "status_code": 400,
                    "status": "error",
                    "error": f"{provider}_configuration_failed",
                    "message": (
                        f"Failed to configure {provider} for {number}: {str(e)}. "
                        f"Ensure the number exists in your {provider} account."
                    ),
                    "sip_trunk_id": trunk_id,
                    "sip_dispatch_rule_id": rule_id,
                    "sip_uri": sip_uri,
                },
                status_code=400,
            )

        return JSONResponse(
            {
                "status_code": 200,
                "status": "success",
                "name": name,
                "org_id": org_id,
                "org_config_id": org_config_id,
                "sip_trunk_id": trunk_id,
                "sip_dispatch_rule_id": rule_id,
                "sip_uri": sip_uri,
                "provider": provider,
                "provider_response": provider_response,
            }
        )
    except Exception as e:
        logger.error("Error during SIP setup: %s", e)
        logger.error(traceback.format_exc())
        return JSONResponse({"error": str(e)}, status_code=500)
