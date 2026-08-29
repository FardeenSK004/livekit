"""Agent runtime and lifecycle configuration."""

import os
from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    """Configuration for LiveKit Agent Server and Session."""

    agent_name: str = Field(
        default_factory=lambda: os.getenv("AGENT_NAME", "mantra-agent")
    )
    num_idle_processes: int = Field(
        default_factory=lambda: int(os.getenv("AGENT_IDLE_PROCESSES", "20"))
    )
    shutdown_process_timeout: float = Field(
        default_factory=lambda: float(os.getenv("AGENT_SHUTDOWN_TIMEOUT", "120.0"))
    )
    amd_enabled: bool = Field(
        default_factory=lambda: os.getenv("AMD_ENABLED", "1") == "1"
    )
    post_call_llm_model: str = Field(
        default_factory=lambda: os.getenv("POST_CALL_LLM_MODEL", "deepseek-v4-pro")
    )
    default_llm_model: str = Field(
        default_factory=lambda: os.getenv("DEFAULT_LLM_MODEL", "deepseek")
    )
    default_voice: str = Field(
        default_factory=lambda: os.getenv("DEFAULT_VOICE", "arushi")
    )
    default_voice_speed: float = Field(
        default_factory=lambda: float(os.getenv("DEFAULT_VOICE_SPEED", "1.0"))
    )


agent_config = AgentConfig()
