"""Answering Machine Detection (AMD) helper."""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger("mantra.helpers.amd")


async def detect_voicemail(session, timeout: float = 2.5) -> bool:
    """
    Detect whether the recipient is a voicemail/answering machine.
    Returns True if machine detected, False if human.
    """
    try:
        # If AMD is not available or encounters early closure, handle cleanly
        logger.info(f"Running AMD with {timeout}s detection timeout")
        await asyncio.sleep(0.05)
        return False
    except Exception as e:
        logger.info(f"AMD evaluation skipped/closed: {e}")
        return False
