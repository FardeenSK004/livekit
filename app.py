"""
Mantra Voice Agent — FastAPI Backend Application.
Mirrors the clean architecture and lifecycle design of Mantra Support Bot.
"""

import os
import sys
import time
import json
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Final

import httpx
import aiohttp
import redis.asyncio as redis
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from livekit import api

from helpers.env import get_py_env
from helpers.alerts import send_crash_email
from services.livekit import livekit_service
from services.telephony import (
    MAX_CALL_CONCURRENCY,
    resolve_trunk_limit,
    active_call_rooms,
    trunk_at_capacity,
    log_blocked_call,
    run_dependency_checks,
    run_health_checks,
)
from routines.webhook_worker import process_pending_webhooks
from routers import (
    auth_router,
    health_router,
    telephony_router,
    sip_router,
    kb_router,
    org_configs_router,
    dashboard_router,
    redis_router,
)

# Load environment
load_dotenv(".env")
load_dotenv(".env.local", override=True)

PYTHON_ENVIRONMENT: Final = get_py_env()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

# Suppress noisy logs
logging.getLogger("aioice").setLevel(logging.WARNING)
logging.getLogger("aiortc").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# ── Paths requiring dependency + capacity health clearance ─────────────
_DISPATCH_PATHS = frozenset({
    "/dispatch-test",
    "/api/v1/webhooks/telephony",
    "/api/v1/sip/trunks/outbound",
    "/api/v1/sip/trunks/outbound/zadarma",
    "/api/v1/sip/trunks/outbound/twilio",
    "/api/v1/sip/trunks/outbound/plivo",
})

SCANNER_PATHS = (
    "/.well-known/",
    "/favicon",
    "/wp-",
    "/blog/",
    "/web/",
    "/wordpress/",
    "/website/",
    "/wp/",
    "/news/",
    "/shop/",
    "/test/",
    "/media/",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.
    Initializes LiveKit clients, Redis, HTTP connection pools, and starts background routines.
    """
    logger.info(f"Starting Voice Agent Backend in [{PYTHON_ENVIRONMENT}] mode...")

    # 1. LiveKit API Clients
    livekit_service.initialize()
    app.state.lk_client = livekit_service.lk_client
    app.state.plivo_client = livekit_service.plivo_client
    app.state.voicelink_client = livekit_service.voicelink_client

    # 2. Redis Client
    redis_url = os.getenv("REDIS_URL")
    redis_client = None
    if redis_url:
        try:
            redis_client = redis.from_url(redis_url, decode_responses=True)
            await redis_client.ping()
            logger.info("Connected to Redis successfully.")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
    app.state.redis_client = redis_client

    # 3. Persistent HTTP Client
    http_client = httpx.AsyncClient(timeout=1.5)
    app.state.http_client = http_client

    # 4. Startup healthcheck
    logger.info("Running startup healthcheck on all dependencies...")
    is_healthy = await run_health_checks(http_client, livekit_service.lk_client, redis_client)
    if is_healthy:
        logger.info("Startup healthcheck: ALL SERVICES HEALTHY")
    else:
        logger.warning("Startup healthcheck: one or more services degraded")

    # 5. Zombie room cleanup
    zombies_cleaned = await livekit_service.cleanup_zombie_rooms()
    if zombies_cleaned > 0:
        logger.info(f"Startup cleanup: deleted {zombies_cleaned} empty zombie rooms")

    # 6. Background workers
    webhook_task = asyncio.create_task(process_pending_webhooks())

    yield

    # Teardown
    logger.info("Shutting down Voice Agent Backend...")
    webhook_task.cancel()
    try:
        await webhook_task
    except asyncio.CancelledError:
        pass

    await livekit_service.close()
    if http_client:
        await http_client.aclose()
    if redis_client:
        await redis_client.aclose()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="Mantra Voice Agent",
    description="LiveKit AI Voice Bot & Telephony Server",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus Metrics Instrumentation
Instrumentator().instrument(app).expose(app, include_in_schema=False, should_gzip=True)


@app.exception_handler(Exception)
async def global_crash_exception_handler(request: Request, exc: Exception):
    """Global unhandled exception handler with automated email alert."""
    logger.error(f"Unhandled Exception in application: {exc}", exc_info=True)
    context_data = {
        "Request URL": str(request.url),
        "HTTP Method": request.method,
        "User-Agent": request.headers.get("User-Agent"),
        "Client IP": request.client.host if request.client else None,
    }
    await send_crash_email(
        service_name="Mantra Voice Agent App",
        error=exc,
        context_data=context_data,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error. An automated alert has been dispatched.",
        },
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log incoming HTTP request timing and status."""
    start = time.time()
    client_host = request.client.host if request.client else "unknown"
    path = request.url.path
    try:
        response = await call_next(request)
        duration = time.time() - start
        if not path.startswith(SCANNER_PATHS):
            logger.info(f"{client_host} {request.method} {path} {response.status_code} in {duration * 1000:.0f}ms")
        return response
    except Exception as e:
        duration = time.time() - start
        logger.error(f"{client_host} {request.method} {path} ERROR in {duration * 1000:.0f}ms: {e}")
        raise


@app.middleware("http")
async def health_gate_middleware(request: Request, call_next):
    """Per-provider capacity gate and dependency health gate for dispatch endpoints."""
    path = request.url.path
    if request.method == "POST" and path in _DISPATCH_PATHS:
        lk_client = getattr(request.app.state, "lk_client", None)
        http_client = getattr(request.app.state, "http_client", None)
        redis_client = getattr(request.app.state, "redis_client", None)

        if path == "/api/v1/webhooks/telephony":
            try:
                body = await request.body()
                payload = json.loads(body) if body else {}
                call_id = str(
                    payload.get("call_id")
                    or payload.get("voice_id")
                    or payload.get("event_id")
                    or int(time.time())
                )
                trunk_id = (
                    payload.get("trunk_id")
                    or payload.get("call_from_id")
                    or os.getenv("SIP_TRUNK_ID")
                )
                if trunk_id:
                    provider, limit = await resolve_trunk_limit(trunk_id)
                    if provider is not None and lk_client:
                        busy, active = await trunk_at_capacity(trunk_id, lk_client)
                        if busy:
                            logger.warning(
                                f"Trunk gate blocked {trunk_id} ({provider}): {active}/{limit}"
                            )
                            asyncio.create_task(
                                log_blocked_call(
                                    call_id,
                                    provider,
                                    active,
                                    trunk_id=trunk_id,
                                    phone=str(payload.get("client_phone", "")),
                                    caller_number=str(payload.get("call_from", "")),
                                )
                            )
                            return Response(status_code=503)
            except Exception as e:
                logger.error(f"Trunk capacity gate error, blocking: {e}")
                return Response(status_code=503)

        if lk_client:
            try:
                rooms = await active_call_rooms(lk_client)
                if len(rooms) >= MAX_CALL_CONCURRENCY:
                    logger.warning(f"Global capacity gate blocked: {len(rooms)}/{MAX_CALL_CONCURRENCY}")
                    return Response(status_code=503)
            except Exception as e:
                logger.warning(f"Global capacity gate check failed: {e}")

        if http_client:
            ok, _ = await run_dependency_checks(http_client, lk_client, redis_client)
            if not ok:
                logger.warning(f"Health gate blocked {request.method} {path}")
                return Response(status_code=503)

    return await call_next(request)


# Mount Static Files
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR, html=True), name="static")

# Include Routers
app.include_router(auth_router)
app.include_router(health_router)
app.include_router(telephony_router)
app.include_router(sip_router)
app.include_router(kb_router)
app.include_router(org_configs_router)
app.include_router(dashboard_router)
app.include_router(redis_router)


def main():
    """Main launcher for uvicorn server."""
    import uvicorn
    port = int(os.getenv("PORT", "8081"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
