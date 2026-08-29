"""Health check endpoints."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from controllers.health import health_controller

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health(request: Request):
    """Run full system dependency and capacity health checks."""
    healthy = await health_controller.check_health(request)
    return JSONResponse(content={"healthy": healthy})
