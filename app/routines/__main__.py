"""CLI entrypoint: ``python -m app.routines`` starts the dispatcher loop."""

from __future__ import annotations

import asyncio
import logging

from dotenv import load_dotenv

from app.config import settings
from app.config.logging import setup_logger
from app.routines.dispatcher_loop import dispatcher_loop
from app.services.livekit import livekit_service
from app.services.redis import redis_service

load_dotenv(".env")
load_dotenv(".env.local", override=True)

logger = setup_logger("app.routines")


async def _run():
    await livekit_service.start()
    await redis_service.start()
    logger.info(
        "Dispatcher started. Limits: MaxConcurrency=%s, Agent=%s, LiveKit=%s",
        settings.MAX_CONCURRENCY,
        settings.AGENT_MAX_WORKERS,
        settings.LIVEKIT_MAX_ROOMS,
    )
    try:
        await dispatcher_loop()
    finally:
        await livekit_service.stop()
        await redis_service.stop()
        logger.info("Dispatcher shutdown gracefully.")


def main():
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("Dispatcher stopped by user.")


if __name__ == "__main__":
    main()
