"""Callable agent tools for LiveKit session."""

from typing import Annotated, Optional
import logging
from livekit.agents import llm

logger = logging.getLogger("core.tools.call_tools")


class EndCallTool:
    """Tool to end the call gracefully."""

    @staticmethod
    def create_tool(end_call_fn):
        @llm.ai_callable(description="End the call gracefully when the user wants to hang up or the conversation is over.")
        async def end_call():
            logger.info("Agent called end_call tool")
            await end_call_fn()
            return "Call ending."
        return end_call
