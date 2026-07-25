"""Capacity checks for the dispatcher."""

from app.config import settings


async def has_capacity(active_count: int) -> bool:
    """Check if we can accept more calls."""
    limits = [
        settings.MAX_CONCURRENCY,
        settings.LIVEKIT_MAX_ROOMS,
        settings.AGENT_MAX_WORKERS,
    ]
    effective_limit = min(limits)
    return active_count < effective_limit


def effective_limit() -> int:
    return min(
        settings.MAX_CONCURRENCY,
        settings.LIVEKIT_MAX_ROOMS,
        settings.AGENT_MAX_WORKERS,
    )
