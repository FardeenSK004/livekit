"""Dispatcher background loop — polls Redis queue and dispatches calls."""

from __future__ import annotations

import asyncio
import json
import logging
import time

from app.dispatcher.capacity import has_capacity
from app.dispatcher.worker import dispatch_call
from app.routines.zombie_cleanup import run_cleanup_once
from app.services.redis import redis_service
from app.services.telemetry import report_telemetry

logger = logging.getLogger("app.routines.dispatcher")


async def dispatcher_loop(interval: float = 0.5, zombie_interval: float = 60.0):
    """Main dispatcher loop — runs forever (mantra/dispatcher.py parity)."""
    logger.info("Dispatcher loop started")
    last_zombie_check = time.time()

    while True:
        try:
            now = time.time()
            if now - last_zombie_check > zombie_interval:
                await run_cleanup_once()
                last_zombie_check = now

            await _process_next_call()
        except Exception as e:
            logger.error("Dispatcher error: %s", e, exc_info=True)
        await asyncio.sleep(interval)


async def _process_next_call():
    """Pop and process the next pending call."""
    active_count = await redis_service.active_count()
    if not await has_capacity(active_count):
        return

    results = await redis_service.client.zpopmin("queue:pending")
    if not results:
        return

    call_entry, score = results[0]
    payload = json.loads(call_entry)
    call_id = payload.get("call_id") or payload.get("voice_id")
    room_name = payload.get("_resolved_room_name", f"call_{call_id}")

    tos_task_id = payload.get("metadata", {}).get("tos_task_id")

    logger.info(
        "Dequeued call %s. Capacity before: %s", call_id, active_count
    )

    if tos_task_id:
        asyncio.create_task(
            report_telemetry(
                tos_task_id=tos_task_id,
                message=f"[Dispatcher] call_dequeued — call_id={call_id}",
                call_id=str(call_id),
            )
        )

    await redis_service.add_active(call_id, room_name)
    await redis_service.set_call_status(call_id, "dispatching")

    success = await dispatch_call(payload)
    if success:
        await redis_service.set_call_status(call_id, "in_progress")
        if tos_task_id:
            asyncio.create_task(
                report_telemetry(
                    tos_task_id=tos_task_id,
                    message=f"[Dispatcher] call_dispatched — call_id={call_id}",
                    call_id=str(call_id),
                )
            )
        return

    logger.error("Failed to dispatch %s. Re-queueing...", call_id)
    await redis_service.remove_active(call_id)
    await redis_service.client.zadd("queue:pending", {call_entry: score + 10})
    await redis_service.set_call_status(call_id, "failed_dispatch_requeued")

    if tos_task_id:
        asyncio.create_task(
            report_telemetry(
                tos_task_id=tos_task_id,
                message=f"[Dispatcher] dispatch_failed — call_id={call_id}",
                call_id=str(call_id),
            )
        )
