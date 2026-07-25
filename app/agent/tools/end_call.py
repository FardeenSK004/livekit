"""end_call tool implementation."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

from livekit.agents import AgentSession, JobContext

logger = logging.getLogger("app.agent.tools.end_call")


async def execute_end_call(
    *,
    session: Optional[AgentSession],
    ctx: Optional[JobContext],
    force_disconnect: Callable,
    create_bg_task: Callable,
) -> str:
    logger.info(
        "Agent decided to end the call via function tool. "
        "Waiting for speech to finish before disconnecting."
    )

    async def graceful_disconnect():
        if session:
            try:
                await asyncio.wait_for(session.wait_for_inactive(), timeout=12.0)
                logger.info(
                    "Agent finished speaking. Pausing briefly before disconnect."
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Agent did not finish speaking within 12s. Disconnecting anyway."
                )
        else:
            await asyncio.sleep(4.0)
        await asyncio.sleep(1.0)
        if ctx:
            await force_disconnect()

    create_bg_task(graceful_disconnect())
    return "Call is ending. Say a brief, warm goodbye now."
