"""LiveKit API and room management service."""

import logging
import os
from typing import List, Optional
import aiohttp
from livekit import api

logger = logging.getLogger("services.livekit")


class LiveKitService:
    """Service for managing LiveKit API clients, rooms, and participants."""

    def __init__(self):
        self.api_key = os.getenv("LIVEKIT_API_KEY")
        self.api_secret = os.getenv("LIVEKIT_API_SECRET")
        self.lk_url = os.getenv("LIVEKIT_URL")
        self.lk_client: Optional[api.LiveKitAPI] = None
        self.plivo_client: Optional[api.LiveKitAPI] = None
        self.plivo_session: Optional[aiohttp.ClientSession] = None
        self.voicelink_client: Optional[api.LiveKitAPI] = None
        self.voicelink_session: Optional[aiohttp.ClientSession] = None

    def initialize(self):
        if not self.lk_url:
            return

        api_url = (
            self.lk_url.replace("wss://", "https://")
            if self.lk_url.startswith("wss://")
            else (
                self.lk_url.replace("ws://", "http://")
                if self.lk_url.startswith("ws://")
                else self.lk_url
            )
        )

        logger.info(f"Connecting to LiveKit API at {api_url}")
        self.lk_client = api.LiveKitAPI(url=api_url, api_key=self.api_key, api_secret=self.api_secret)

        plivo_proxy = os.getenv("PLIVO_PROXY")
        self.plivo_session = aiohttp.ClientSession(proxy=plivo_proxy)
        self.plivo_client = api.LiveKitAPI(
            url=api_url, api_key=self.api_key, api_secret=self.api_secret, session=self.plivo_session
        )

        voicelink_proxy = os.getenv("VOICELINK_PROXY") or plivo_proxy
        self.voicelink_session = aiohttp.ClientSession(proxy=voicelink_proxy)
        self.voicelink_client = api.LiveKitAPI(
            url=api_url, api_key=self.api_key, api_secret=self.api_secret, session=self.voicelink_session
        )

    async def close(self):
        for client in [self.lk_client, self.plivo_client, self.voicelink_client]:
            if client:
                await client.aclose()
        if self.plivo_session:
            await self.plivo_session.close()
        if self.voicelink_session:
            await self.voicelink_session.close()

    async def cleanup_zombie_rooms(self) -> int:
        """Delete active call rooms with 0 participants."""
        if not self.lk_client:
            return 0
        try:
            response = await self.lk_client.room.list_rooms(api.ListRoomsRequest())
            zombie_count = 0
            for room in response.rooms:
                if not room.name or not room.name.startswith("call_"):
                    continue
                if room.num_participants == 0:
                    try:
                        await self.lk_client.room.delete_room(api.DeleteRoomRequest(room=room.name))
                        zombie_count += 1
                    except Exception as e:
                        logger.error(f"Failed to delete zombie room {room.name}: {e}")
            return zombie_count
        except Exception as e:
            logger.error(f"Zombie room cleanup failed: {e}")
            return 0


livekit_service = LiveKitService()
