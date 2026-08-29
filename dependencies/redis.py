"""Redis client dependency for FastAPI."""

import os
from typing import Annotated, Optional
import redis.asyncio as redis
from fastapi import Depends, Request

_redis_client: Optional[redis.Redis] = None


async def get_redis_client(request: Optional[Request] = None) -> Optional[redis.Redis]:
    """Retrieve global or request-bound Redis async client."""
    global _redis_client
    if request is not None and hasattr(request.app.state, "redis_client"):
        return request.app.state.redis_client

    if _redis_client is None:
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            _redis_client = redis.from_url(redis_url, decode_responses=True)
    return _redis_client


RedisService = Annotated[Optional[redis.Redis], Depends(get_redis_client)]

__all__ = ["get_redis_client", "RedisService"]
