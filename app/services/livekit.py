"""LiveKit API client management and SIP/dispatch helpers."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import aiohttp
from livekit import api
from livekit.protocol import sip as proto_sip

from app.config import settings

logger = logging.getLogger("app.services.livekit")

DEFAULT_PROVIDER = "zadarma"
AGENT_NAME = "mantra-agent"


class LiveKitService:
    """Manages LiveKit API clients (direct + Plivo proxy)."""

    def __init__(self):
        self._lk_client: api.LiveKitAPI | None = None
        self._plivo_client: api.LiveKitAPI | None = None
        self._plivo_session: aiohttp.ClientSession | None = None

    async def start(self):
        api_key = settings.LIVEKIT_API_KEY
        api_secret = settings.LIVEKIT_API_SECRET
        lk_url = self._normalize_url(settings.LIVEKIT_URL)

        if not lk_url:
            return

        self._lk_client = api.LiveKitAPI(
            url=lk_url, api_key=api_key, api_secret=api_secret
        )

        proxy = settings.plivo_proxy or None
        self._plivo_session = aiohttp.ClientSession(proxy=proxy)
        self._plivo_client = api.LiveKitAPI(
            url=lk_url,
            api_key=api_key,
            api_secret=api_secret,
            session=self._plivo_session,
        )

    async def stop(self):
        if self._lk_client:
            await self._lk_client.aclose()
            self._lk_client = None
        if self._plivo_client:
            await self._plivo_client.aclose()
            self._plivo_client = None
        if self._plivo_session:
            await self._plivo_session.close()
            self._plivo_session = None

    @property
    def lk(self) -> api.LiveKitAPI:
        if not self._lk_client:
            raise RuntimeError("LiveKit client not initialized. Call start() first.")
        return self._lk_client

    @property
    def plivo(self) -> api.LiveKitAPI:
        if not self._plivo_client:
            return self.lk
        return self._plivo_client

    def get_client_for_provider(self, provider: str) -> api.LiveKitAPI:
        if provider == "plivo":
            return self.plivo
        return self.lk

    @staticmethod
    def _normalize_url(url: str) -> str:
        if not url:
            return ""
        if url.startswith("wss://"):
            return url.replace("wss://", "https://", 1)
        if url.startswith("ws://"):
            return url.replace("ws://", "http://", 1)
        return url

    @staticmethod
    def get_sip_domain() -> str:
        configured = settings.LIVEKIT_SIP_DOMAIN or settings.SIP_DOMAIN
        if configured:
            return configured
        lk_url = settings.LIVEKIT_URL or ""
        host_lk = (
            lk_url.replace("wss://", "")
            .replace("ws://", "")
            .replace("https://", "")
            .replace("http://", "")
        )
        if "livekit.cloud" in host_lk:
            subdomain = host_lk.split(".")[0]
            if subdomain and subdomain != "www":
                return f"{subdomain}.sip.livekit.cloud"
        return "sip.livekit.cloud"

    def create_access_token(
        self,
        identity: str,
        name: str,
        room_name: str,
        *,
        can_publish: bool = True,
        can_subscribe: bool = True,
    ) -> str:
        token = (
            api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
            .with_identity(identity)
            .with_name(name)
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=can_publish,
                    can_subscribe=can_subscribe,
                )
            )
        )
        return token.to_jwt()

    async def create_room(self, room_name: str, **kwargs) -> None:
        await self.lk.room.create_room(api.CreateRoomRequest(name=room_name, **kwargs))

    async def delete_room(self, room_name: str) -> None:
        await self.lk.room.delete_room(api.DeleteRoomRequest(room=room_name))

    async def list_rooms(self) -> list:
        resp = await self.lk.room.list_rooms(api.ListRoomsRequest())
        return list(resp.rooms)

    async def create_agent_dispatch(self, room_name: str, metadata: dict | str):
        meta = metadata if isinstance(metadata, str) else json.dumps(metadata)
        return await self.lk.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                room=room_name, agent_name=AGENT_NAME, metadata=meta
            )
        )

    async def create_sip_participant(
        self,
        room_name: str,
        sip_trunk_id: str,
        sip_call_to: str,
        *,
        sip_number: str | None = None,
        participant_identity: str | None = None,
        participant_name: str = "SIP Caller",
        play_dialtone: bool = True,
        play_ringtone: bool = False,
        wait_until_answered: bool = False,
        provider: str = "",
    ):
        req = proto_sip.CreateSIPParticipantRequest(
            room_name=room_name,
            sip_trunk_id=sip_trunk_id,
            sip_call_to=sip_call_to,
            play_dialtone=play_dialtone,
        )
        if sip_number:
            req.sip_number = sip_number
        if participant_identity:
            req.participant_identity = participant_identity
        if participant_name:
            req.participant_name = participant_name
        if play_ringtone:
            req.play_ringtone = play_ringtone
        if wait_until_answered:
            req.wait_until_answered = wait_until_answered

        client = self.get_client_for_provider(provider) if provider else self.lk
        return await client.sip.create_sip_participant(req)

    async def get_provider_from_trunk(self, trunk_id: str) -> str:
        try:
            response = await self.lk.sip.list_outbound_trunk(
                api.ListSIPOutboundTrunkRequest(trunk_ids=[trunk_id])
            )
            if response.items:
                address = (response.items[0].address or "").lower()
                if "twilio" in address:
                    return "twilio"
                if "plivo" in address:
                    return "plivo"
                return DEFAULT_PROVIDER
            logger.warning("Trunk %s not found — defaulting to %s", trunk_id, DEFAULT_PROVIDER)
            return DEFAULT_PROVIDER
        except Exception as e:
            logger.error("Failed to fetch trunk %s for provider detection: %s", trunk_id, e)
            return DEFAULT_PROVIDER

    async def create_inbound_trunk(
        self,
        name: str,
        numbers: list[str],
        auth_username: str = "",
        auth_password: str = "",
    ):
        trunk_request = api.CreateSIPInboundTrunkRequest(
            trunk=api.SIPInboundTrunkInfo(
                name=name,
                numbers=numbers,
                auth_username=auth_username or "",
                auth_password=auth_password or "",
            )
        )
        return await self.lk.sip.create_inbound_trunk(trunk_request)

    async def list_inbound_trunks(self):
        return await self.lk.sip.list_inbound_trunk(api.ListSIPInboundTrunkRequest())

    async def delete_trunk(self, trunk_id: str):
        return await self.lk.sip.delete_trunk(
            api.DeleteSIPTrunkRequest(sip_trunk_id=trunk_id)
        )

    async def update_inbound_trunk_fields(self, trunk_id: str, **kwargs):
        return await self.lk.sip.update_inbound_trunk_fields(trunk_id, **kwargs)

    async def create_outbound_trunk(
        self,
        name: str,
        address: str,
        numbers: list[str],
        auth_username: str,
        auth_password: str,
        destination_country: str | None = None,
        client: api.LiveKitAPI | None = None,
    ):
        svc = (client or self.lk).sip
        trunk_request = api.CreateSIPOutboundTrunkRequest(
            trunk=api.SIPOutboundTrunkInfo(
                name=name,
                address=address,
                numbers=numbers,
                auth_username=auth_username,
                auth_password=auth_password,
                destination_country=destination_country,
            )
        )
        return await svc.create_outbound_trunk(trunk_request)

    async def list_outbound_trunks(self, trunk_ids: list[str] | None = None):
        req = api.ListSIPOutboundTrunkRequest()
        if trunk_ids:
            req.trunk_ids.extend(trunk_ids)
        return await self.lk.sip.list_outbound_trunk(req)

    async def create_dispatch_rule(
        self,
        name: str,
        trunk_ids: list[str],
        metadata: dict | str,
        room_prefix: str = "inbound_",
        room_config: api.RoomConfiguration | None = None,
    ):
        meta = metadata if isinstance(metadata, str) else json.dumps(metadata)
        kwargs: dict[str, Any] = {
            "name": name,
            "metadata": meta,
            "rule": api.SIPDispatchRule(
                dispatch_rule_individual=api.SIPDispatchRuleIndividual(
                    room_prefix=room_prefix
                )
            ),
            "trunk_ids": trunk_ids,
        }
        if room_config is not None:
            kwargs["room_config"] = room_config
        return await self.lk.sip.create_sip_dispatch_rule(
            api.CreateSIPDispatchRuleRequest(**kwargs)
        )

    async def list_dispatch_rules(self):
        return await self.lk.sip.list_dispatch_rule(api.ListSIPDispatchRuleRequest())

    async def delete_dispatch_rule(self, rule_id: str):
        return await self.lk.sip.delete_dispatch_rule(
            api.DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=rule_id)
        )

    async def update_dispatch_rule_fields(self, rule_id: str, **kwargs):
        return await self.lk.sip.update_dispatch_rule_fields(rule_id, **kwargs)

    async def find_inbound_trunk_for_number(self, number: str) -> str | None:
        clean_number = number.replace("+", "")
        try:
            response = await self.list_inbound_trunks()
            for item in response.items:
                trunk_numbers = list(item.numbers)
                if number in trunk_numbers or clean_number in trunk_numbers:
                    return item.sip_trunk_id
        except Exception as e:
            logger.warning("Could not list inbound trunks: %s", e)
        return None

    async def find_dispatch_rule_for_trunk(self, trunk_id: str) -> str | None:
        try:
            rule_response = await self.list_dispatch_rules()
            for item in rule_response.items:
                if trunk_id in list(item.trunk_ids):
                    return item.sip_dispatch_rule_id
        except Exception as e:
            logger.warning("Could not list dispatch rules: %s", e)
        return None


livekit_service = LiveKitService()
