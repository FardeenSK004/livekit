"""SIP call placement and trunk helpers."""

from __future__ import annotations

import json
import logging
from typing import Any

from livekit import api

from app.config import settings
from app.config.constants import SIP_DEFAULT_ADDRESS_TWILIO
from app.models.sip import SIP_ERROR_MAP, SipError
from app.services.livekit import livekit_service
from app.services.redis import redis_service

logger = logging.getLogger("app.services.sip")


def normalize_numbers(numbers: str | list | Any) -> list[str]:
    if isinstance(numbers, str):
        return [n.strip() for n in numbers.split(",") if n.strip()]
    if isinstance(numbers, list):
        return [str(n).strip() for n in numbers]
    return [str(numbers)]


def build_e164_phone(country_code: str, client_phone: str) -> str:
    client_phone = (client_phone or "").strip()
    country_code = (country_code or "").strip("+")
    if client_phone.startswith("+"):
        return client_phone
    if country_code and client_phone:
        return f"+{country_code}{client_phone}"
    return client_phone


def classify_sip_error(error: str) -> str:
    err_str = error.lower()
    if any(token in err_str for token in ("408", "timeout", "no answer")):
        return SipError.NO_ANSWER.value
    if any(token in err_str for token in ("486", "busy", "603", "decline", "rejected")):
        return SipError.BUSY.value
    for code, sip_error in SIP_ERROR_MAP.items():
        if code in err_str:
            return sip_error.value
    return SipError.INCOMPLETE.value


class SipService:
    async def place_call(
        self,
        provider: str,
        phone_number: str,
        room_name: str,
        trunk_id: str = "",
        *,
        sip_number: str | None = None,
        call_id: str | int | None = None,
        wait_until_answered: bool = True,
    ) -> dict:
        if not trunk_id:
            trunk_id = self.resolve_trunk_id(provider)

        try:
            part = await livekit_service.create_sip_participant(
                room_name=room_name,
                sip_trunk_id=trunk_id,
                sip_call_to=phone_number,
                sip_number=sip_number,
                participant_identity=f"sip_{call_id}" if call_id else None,
                participant_name="SIP Caller",
                play_ringtone=False,
                wait_until_answered=wait_until_answered,
                provider=provider,
            )
            return {
                "status": "ringing",
                "error": None,
                "trunk_id": trunk_id,
                "participant": part.participant_identity,
            }
        except Exception as e:
            error = str(e)
            logger.error("SIP place_call failed: %s", error)
            return {
                "status": classify_sip_error(error),
                "error": error,
                "trunk_id": trunk_id,
            }

    async def set_sip_error_status(self, call_id: str, error: str):
        await redis_service.set_sip_error(call_id, error)

    async def handle_sip_failure(self, call_id: str, room_name: str, error: Exception):
        status_guess = classify_sip_error(str(error))
        try:
            await redis_service.set_sip_error(str(call_id), status_guess)
        except Exception as re:
            logger.error("Failed to save SIP error to Redis: %s", re)
        try:
            await livekit_service.delete_room(room_name)
            logger.info("Deleted room %s due to SIP failure", room_name)
        except Exception as cleanup_err:
            logger.error("Failed to cleanup room after SIP failure: %s", cleanup_err)

    def resolve_trunk_id(self, provider: str) -> str:
        if provider == "twilio":
            return settings.SIP_TRUNK_ID_TWILIO or settings.SIP_TRUNK_ID
        if provider == "zadarma":
            return settings.SIP_TRUNK_ID_ZADARMA or settings.SIP_TRUNK_ID
        return settings.SIP_TRUNK_ID

    async def get_provider_from_trunk(self, trunk_id: str) -> str:
        return await livekit_service.get_provider_from_trunk(trunk_id)

    async def create_outbound_trunk(
        self,
        payload: dict,
        *,
        provider: str = "zadarma",
        client=None,
        destination_country: str | None = None,
    ):
        name = payload.get("name")
        address = payload.get("address") or (
            SIP_DEFAULT_ADDRESS_TWILIO if provider == "twilio" else payload.get("address")
        )
        numbers = normalize_numbers(payload.get("numbers", []))
        auth_username = (
            payload.get("authUsername")
            or payload.get("auth_username")
            or payload.get("auth_user")
        )
        auth_password = (
            payload.get("authPassword")
            or payload.get("auth_password")
            or payload.get("auth_pass")
        )
        if not all([name, address, numbers, auth_username, auth_password]):
            missing = [
                f
                for f, v in [
                    ("name", name),
                    ("address", address),
                    ("numbers", numbers),
                    ("auth_username", auth_username),
                    ("auth_password", auth_password),
                ]
                if not v
            ]
            raise ValueError(f"Missing required fields: {', '.join(missing)}")

        return await livekit_service.create_outbound_trunk(
            name=name,
            address=address,
            numbers=numbers,
            auth_username=auth_username,
            auth_password=auth_password,
            destination_country=destination_country,
            client=client,
        )

    async def update_inbound_trunk(self, trunk_id: str, payload: dict):
        kwargs: dict[str, Any] = {}
        if "name" in payload:
            kwargs["name"] = payload["name"]
        if "metadata" in payload:
            kwargs["metadata"] = (
                json.dumps(payload["metadata"])
                if isinstance(payload["metadata"], dict)
                else payload["metadata"]
            )
        if "auth_username" in payload:
            kwargs["auth_username"] = payload["auth_username"]
        if "auth_password" in payload:
            kwargs["auth_password"] = payload["auth_password"]
        if "numbers" in payload:
            kwargs["numbers"] = normalize_numbers(payload["numbers"])
        if "allowed_addresses" in payload:
            kwargs["allowed_addresses"] = normalize_numbers(payload["allowed_addresses"])
        if "allowed_numbers" in payload:
            kwargs["allowed_numbers"] = normalize_numbers(payload["allowed_numbers"])
        if not kwargs:
            raise ValueError("No updatable fields provided")
        await livekit_service.update_inbound_trunk_fields(trunk_id, **kwargs)

    async def update_dispatch_rule(self, rule_id: str, payload: dict):
        from livekit.protocol import sip as proto_sip

        kwargs: dict[str, Any] = {}
        if "name" in payload:
            kwargs["name"] = payload["name"]
        if "metadata" in payload:
            kwargs["metadata"] = (
                json.dumps(payload["metadata"])
                if isinstance(payload["metadata"], dict)
                else payload["metadata"]
            )
        if "attributes" in payload and isinstance(payload["attributes"], dict):
            kwargs["attributes"] = payload["attributes"]
        if "trunk_ids" in payload:
            kwargs["trunk_ids"] = normalize_numbers(payload["trunk_ids"])
        if "rule" in payload:
            rule_config = payload["rule"]
            kwargs["rule"] = proto_sip.SIPDispatchRule(
                dispatch_rule_individual=proto_sip.SIPDispatchRuleIndividual(
                    room_prefix=rule_config.get("room_prefix", "inbound_"),
                    pin=rule_config.get("pin", ""),
                    no_randomness=rule_config.get("no_randomness", False),
                )
            )
        if not kwargs:
            raise ValueError("No updatable fields provided")
        await livekit_service.update_dispatch_rule_fields(rule_id, **kwargs)


sip_service = SipService()
