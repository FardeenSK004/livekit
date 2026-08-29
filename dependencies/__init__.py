"""Dependencies package for FastAPI route handlers."""

from dependencies.database import get_db_connection, DatabaseConnectionService
from dependencies.redis import get_redis_client, RedisService
from dependencies.livekit import (
    get_livekit_client,
    get_plivo_client,
    get_voicelink_client,
    LiveKitClientService,
)
from dependencies.auth import require_auth, AuthUser

__all__ = [
    "get_db_connection",
    "DatabaseConnectionService",
    "get_redis_client",
    "RedisService",
    "get_livekit_client",
    "get_plivo_client",
    "get_voicelink_client",
    "LiveKitClientService",
    "require_auth",
    "AuthUser",
]
