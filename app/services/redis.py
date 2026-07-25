"""Redis service — queue, active calls, capacity tracking."""

from __future__ import annotations

import json
import time
from typing import Any, Optional

import redis.asyncio as redis

from app.config import settings
from app.config.constants import CALLS_ACTIVE, QUEUE_PENDING


class RedisService:
    def __init__(self):
        self._client: redis.Redis | None = None

    async def start(self):
        self._client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        await self._client.ping()

    async def stop(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> redis.Redis:
        if not self._client:
            raise RuntimeError("Redis not initialized. Call start() first.")
        return self._client

    # ── Queue ──────────────────────────────────────────────────────────
    async def push_pending(self, payload: dict, score: float | None = None):
        if score is None:
            score = time.time()
        await self.client.zadd(QUEUE_PENDING, {json.dumps(payload): score})

    async def pop_pending(self) -> Optional[dict]:
        results = await self.client.zpopmin(QUEUE_PENDING)
        if not results:
            return None
        item, _score = results[0]
        return json.loads(item)

    async def requeue(self, payload: dict, additional_score: float = 10):
        await self.push_pending(payload, time.time() + additional_score)

    async def pending_count(self) -> int:
        return int(await self.client.zcard(QUEUE_PENDING))

    # ── Active Calls (plain room_name STRING per mantra) ───────────────
    async def add_active(self, call_id: str, room_name: str, metadata: dict | None = None):
        """Store call_id -> room_name as a plain string (not JSON)."""
        await self.client.hset(CALLS_ACTIVE, call_id, room_name)

    async def remove_active(self, call_id: str):
        await self.client.hdel(CALLS_ACTIVE, call_id)

    async def get_active(self, call_id: str) -> Optional[str]:
        return await self.client.hget(CALLS_ACTIVE, call_id)

    async def all_active(self) -> list[dict[str, str]]:
        data = await self.client.hgetall(CALLS_ACTIVE)
        return [{"call_id": call_id, "room_name": room_name} for call_id, room_name in data.items()]

    async def active_map(self) -> dict[str, str]:
        return await self.client.hgetall(CALLS_ACTIVE)

    async def active_count(self) -> int:
        return int(await self.client.hlen(CALLS_ACTIVE))

    async def get_call_status(self, call_id: str) -> Optional[str]:
        return await self.client.get(f"calls:status:{call_id}")

    async def set_call_status(self, call_id: str, status: str):
        await self.client.set(f"calls:status:{call_id}", status)

    async def set_provider_trunk_mapping(
        self, provider: str, phone_number: str, trunk_id: str, ttl: int = 86400 * 30
    ):
        await self.client.set(f"{provider}:sip_trunk:{phone_number}", trunk_id, ex=ttl)

    async def get_provider_trunk_mapping(self, provider: str, phone_number: str) -> Optional[str]:
        return await self.client.get(f"{provider}:sip_trunk:{phone_number}")

    # ── SIP Error Status ───────────────────────────────────────────────
    async def set_sip_error(self, call_id: str, error: str, ttl: int = 300):
        key = f"sip_error_status:{call_id}"
        await self.client.setex(key, ttl, error)

    async def get_sip_error(self, call_id: str) -> Optional[str]:
        key = f"sip_error_status:{call_id}"
        return await self.client.get(key)


redis_service = RedisService()
