"""Dashboard UI pages and streaming endpoints."""

import os
import json
import time
import asyncio
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from controllers.dashboard import dashboard_controller

router = APIRouter(tags=["Dashboard"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")


@router.get("/dashboard")
async def dashboard_page():
    return FileResponse(os.path.join(STATIC_DIR, "dashboard.html"))


@router.get("/console")
async def console_page():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@router.get("/network")
async def network_page():
    return FileResponse(os.path.join(STATIC_DIR, "network.html"))


@router.get("/redis")
async def redis_page():
    return FileResponse(os.path.join(STATIC_DIR, "redis.html"))


@router.get("/kb-chat")
async def kb_chat_page():
    return FileResponse(os.path.join(STATIC_DIR, "kb_chat.html"))


@router.get("/config")
async def get_config():
    return JSONResponse({"url": os.getenv("LIVEKIT_URL")})


@router.get("/api/v1/dashboard/stream")
async def dashboard_stream(request: Request):
    redis_client = getattr(request.app.state, "redis_client", None)

    async def event_generator():
        if not redis_client:
            yield 'data: {"error": "Redis not connected"}\n\n'
            return

        MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "5"))

        while True:
            try:
                pending_count = await redis_client.zcard("queue:pending")
                active_calls_map = await redis_client.hgetall("calls:active")
                active_count = len(active_calls_map)

                active_details = []
                for call_id, room_name in active_calls_map.items():
                    status = await redis_client.get(f"calls:status:{call_id}")
                    active_details.append({
                        "call_id": call_id,
                        "room_name": room_name,
                        "status": status or "unknown",
                    })

                data = json.dumps({
                    "pending_calls": pending_count,
                    "active_calls": active_count,
                    "max_concurrency": MAX_CONCURRENCY,
                    "active_call_details": active_details,
                    "timestamp": time.time(),
                })
                yield f"data: {data}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

            await asyncio.sleep(2)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/api/v1/dashboard/metrics")
async def dashboard_metrics():
    return await dashboard_controller.get_metrics()


@router.get("/api/v1/dashboard/calls")
async def dashboard_calls(limit: int = 20, offset: int = 0, search: str = None, status: str = None):
    return await dashboard_controller.get_calls(limit=limit, offset=offset, search=search, status=status)


@router.get("/api/v1/dashboard/active-calls")
async def dashboard_active_calls(request: Request):
    return await dashboard_controller.get_active_calls(request)
