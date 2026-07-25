"""Agent state and session models."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class AgentState(BaseModel):
    call_id: str = ""
    room_name: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    handoff_triggered: bool = False
    call_ended: bool = False
    inactivity_task: Optional[Any] = None
    farewell_task: Optional[Any] = None
    call_limiter_task: Optional[Any] = None
    kb_ids: list[str] = Field(default_factory=list)
    kb_tags: list[str] = Field(default_factory=list)


class ToolResult(BaseModel):
    success: bool
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class SessionData(BaseModel):
    room_name: str
    participant_identity: str = ""
    agent_identity: str = ""
    user_joined: bool = False
    user_spoke: bool = False
    started_at: Optional[float] = None
