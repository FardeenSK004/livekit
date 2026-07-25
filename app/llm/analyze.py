"""Post-call LLM analysis — wraps SessionRecorder.analyze_call."""

from __future__ import annotations

import logging
from typing import Any, Optional

from livekit.agents import llm

from app.recording.session_recorder import SessionRecorder

logger = logging.getLogger("app.llm.analyze")


async def analyze_call(
    llm_engine: llm.LLM,
    history: list,
    current_stage_id: Optional[int] = None,
    stage_details: list[dict] | None = None,
    duration: int = 0,
    client_country_code: str = "",
    **_kwargs: Any,
) -> dict[str, Any]:
    """Analyze a call transcript using the production CRM analysis prompt."""
    return await SessionRecorder.analyze_call(
        llm_engine=llm_engine,
        history=history,
        current_stage_id=current_stage_id,
        stage_details=stage_details or [],
        duration=duration,
        client_country_code=client_country_code,
    )
