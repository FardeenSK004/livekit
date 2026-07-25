"""Dashboard API — metrics, SSE stream, call history."""

from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.config import settings
from app.routers.auth import require_auth
from app.services.db import db_service
from app.services.redis import redis_service

logger = logging.getLogger("app.routers.dashboard")

router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_auth)],
)


@router.get("/stream")
async def dashboard_stream(request: Request):
    async def event_generator():
        max_concurrency = settings.MAX_CONCURRENCY or settings.CARTESIA_MAX_CONCURRENCY

        while True:
            try:
                pending_count = await redis_service.pending_count()
                active_map = await redis_service.active_map()
                active_count = len(active_map)

                active_details = []
                for call_id, room_name in active_map.items():
                    status = await redis_service.get_call_status(call_id)
                    active_details.append(
                        {
                            "call_id": call_id,
                            "room_name": room_name,
                            "status": status or "unknown",
                        }
                    )

                data = json.dumps(
                    {
                        "pending_calls": pending_count,
                        "active_calls": active_count,
                        "max_concurrency": max_concurrency,
                        "active_call_details": active_details,
                        "timestamp": time.time(),
                    }
                )
                yield f"data: {data}\n\n"
            except Exception as e:
                logger.error("Dashboard SSE error: %s", e)
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/metrics")
async def dashboard_metrics(request: Request):
    try:
        metrics = await db_service.get_dashboard_metrics()
        answer_rate = (
            round(metrics["completed_calls"] / metrics["total_calls"] * 100, 1)
            if metrics["total_calls"] > 0
            else 0
        )
        return {**metrics, "answer_rate": answer_rate}
    except Exception as e:
        logger.error("Dashboard metrics error: %s", e)
        return {"error": str(e)}


@router.get("/calls")
async def dashboard_calls(request: Request, limit: int = 20, offset: int = 0):
    try:
        calls, total = await db_service.get_dashboard_calls(limit, offset)
        return {"calls": calls, "total": total, "limit": limit, "offset": offset}
    except Exception as e:
        logger.error("Dashboard calls error: %s", e)
        return {"error": str(e), "calls": [], "total": 0}


@router.get("/active-calls")
async def dashboard_active_calls(request: Request):
    try:
        active_map = await redis_service.active_map()
        calls = []
        for call_id, room_name in active_map.items():
            status = await redis_service.get_call_status(call_id)
            calls.append(
                {
                    "call_id": call_id,
                    "room_name": room_name,
                    "status": status or "unknown",
                }
            )
        return {"active_calls": calls}
    except Exception as e:
        logger.error("Active calls error: %s", e)
        return {"active_calls": [], "error": str(e)}
