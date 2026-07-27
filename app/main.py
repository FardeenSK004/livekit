"""FastAPI application factory — replaces mantra/ui_server.py."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config.logging import setup_logger
from app.middleware import register_middleware
from app.routers import auth, dashboard, dispatch, health, kb, org, pages, sip, webhooks
from app.routers.health import _run_health_checks
from app.services import db_service, livekit_service, redis_service
from app.services.s3 import s3_service

load_dotenv(".env")
load_dotenv(".env.local", override=True)

logger = setup_logger("app.main")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting services...")
    await livekit_service.start()
    await redis_service.start()
    await db_service.start()
    try:
        s3_service.start()
    except Exception as e:
        logger.error("S3 start failed (non-fatal): %s", e)
    logger.info("All services started")

    logger.info("Running startup healthcheck on all dependencies...")
    if await _run_health_checks():
        logger.info("Startup healthcheck: ALL SERVICES HEALTHY")
    else:
        logger.warning("Startup healthcheck: one or more services down — refusing dispatch")

    yield
    logger.info("Shutting down services...")
    await livekit_service.stop()
    await redis_service.stop()
    await db_service.stop()
    logger.info("All services stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="Mantra Voice Agent", version="0.1.0", lifespan=lifespan)

    register_middleware(app)

    app.include_router(health.router)
    app.include_router(pages.router)
    app.include_router(auth.router)
    app.include_router(webhooks.router)
    app.include_router(sip.router)
    app.include_router(dashboard.router)
    app.include_router(kb.router)
    app.include_router(kb.knowledge_router)
    app.include_router(dispatch.router)
    app.include_router(org.router)

    if os.path.isdir(STATIC_DIR):
        app.mount("/static", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app


app = create_app()


def main():
    import uvicorn

    port = int(os.getenv("PORT", "8082"))
    logger.info("UI Server starting on http://0.0.0.0:%s", port)
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True, access_log=False)


if __name__ == "__main__":
    main()
