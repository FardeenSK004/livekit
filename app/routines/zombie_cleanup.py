"""Zombie cleanup — reconciles Redis active calls with LiveKit rooms."""

from __future__ import annotations

import asyncio
import logging

from app.services.livekit import livekit_service
from app.services.redis import redis_service

logger = logging.getLogger("app.routines.zombie_cleanup")


async def run_cleanup_once():
    """Remove Redis active entries whose LiveKit rooms no longer exist."""
    active_calls = await redis_service.all_active()
    if not active_calls:
        return

    livekit_rooms = await livekit_service.list_rooms()
    livekit_room_names = {r.name for r in livekit_rooms}

    for call in active_calls:
        room_name = call.get("room_name", "")
        call_id = call.get("call_id", "")
        if room_name and room_name not in livekit_room_names:
            logger.warning(
                "Zombie detected! Room %s not found. Removing call %s from active.",
                room_name,
                call_id,
            )
            await redis_service.remove_active(call_id)
            await redis_service.set_call_status(
                call_id, "completed_or_failed_zombie"
            )


async def zombie_cleanup(interval: float = 60):
    """Periodically clean up stale rooms from Redis."""
    while True:
        try:
            await run_cleanup_once()
        except Exception as e:
            logger.error("Zombie cleanup error: %s", e)
        await asyncio.sleep(interval)
