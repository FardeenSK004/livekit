"""Configurations package for Mantra Voice Agent."""

from configs.agent import AgentConfig, agent_config
from configs.voices import resolve_voice_id

__all__ = ["AgentConfig", "agent_config", "resolve_voice_id"]
