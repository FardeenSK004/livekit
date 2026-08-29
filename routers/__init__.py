"""Routers package for API endpoints."""

from routers.auth import router as auth_router
from routers.health import router as health_router
from routers.telephony import router as telephony_router
from routers.sip import router as sip_router
from routers.kb import router as kb_router
from routers.org_configs import router as org_configs_router
from routers.dashboard import router as dashboard_router
from routers.redis import router as redis_router

__all__ = [
    "auth_router",
    "health_router",
    "telephony_router",
    "sip_router",
    "kb_router",
    "org_configs_router",
    "dashboard_router",
    "redis_router",
]
