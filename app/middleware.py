"""Global exception handler, health gate, and request logging middleware."""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from prometheus_fastapi_instrumentator import Instrumentator

from app.alerter.email import send_crash_email
from app.routers.health import _run_health_checks

logger = logging.getLogger("app.main")

SCANNER_PATHS = (
    "/.well-known/",
    "/favicon",
    "/wp-",
    "/blog/",
    "/web/",
    "/wordpress/",
    "/website/",
    "/wp/",
    "/news/",
    "/2018/",
    "/2019/",
    "/shop/",
    "/wp1/",
    "/test/",
    "/media/",
    "/wp2/",
    "/site/",
    "/cms/",
    "/sito/",
)


def register_middleware(app: FastAPI) -> None:
    Instrumentator().instrument(app).expose(
        app, include_in_schema=False, should_gzip=True
    )

    @app.exception_handler(Exception)
    async def global_crash_exception_handler(request: Request, exc: Exception):
        logger.error("Error in UI server: %s", exc, exc_info=True)
        context_data = {
            "Request URL": str(request.url),
            "HTTP Method": request.method,
            "User-Agent": request.headers.get("User-Agent"),
            "Client IP": request.client.host if request.client else None,
        }
        await send_crash_email(
            service_name="Mantra UI Server", error=exc, context_data=context_data
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": (
                    "Internal server error, An Automated alert has been dispatched. "
                    "The technical team is working on resolving this issue."
                )
            },
        )

    _DISPATCH_PATHS = frozenset({
        "/dispatch-test",
        "/api/v1/webhooks/telephony",
        "/api/v1/sip/trunks/outbound",
        "/api/v1/sip/trunks/outbound/zadarma",
        "/api/v1/sip/trunks/outbound/twilio",
        "/api/v1/sip/trunks/outbound/plivo",
    })

    @app.middleware("http")
    async def health_gate_middleware(request: Request, call_next):
        path = request.url.path
        if request.method == "POST" and path in _DISPATCH_PATHS:
            ok = await _run_health_checks()
            if not ok:
                logger.warning("Health gate blocked %s %s", request.method, path)
                return Response(status_code=503)
        return await call_next(request)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.time()
        client_host = request.client.host if request.client else "unknown"
        path = request.url.path
        try:
            response = await call_next(request)
            duration = time.time() - start
            if path.startswith(SCANNER_PATHS):
                logger.debug(
                    "Scanner: %s %s %s %s",
                    client_host,
                    request.method,
                    path,
                    response.status_code,
                )
            else:
                logger.info(
                    "%s %s %s %s in %.0fms",
                    client_host,
                    request.method,
                    path,
                    response.status_code,
                    duration * 1000,
                )
            return response
        except Exception as e:
            duration = time.time() - start
            logger.error(
                "%s %s %s ERROR in %.0fms: %s",
                client_host,
                request.method,
                path,
                duration * 1000,
                e,
            )
            raise
