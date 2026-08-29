"""Health controller."""

from fastapi import Request
from services.telephony import run_health_checks


class HealthController:
    """Controller for running system health checks."""

    @staticmethod
    async def check_health(request: Request) -> bool:
        http_client = getattr(request.app.state, "http_client", None)
        lk_client = getattr(request.app.state, "lk_client", None)
        redis_client = getattr(request.app.state, "redis_client", None)
        return await run_health_checks(http_client, lk_client, redis_client)


health_controller = HealthController()
