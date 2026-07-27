import asyncio
import logging
import os

import boto3
import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from livekit import api

from app.config import settings
from app.services.livekit import livekit_service

logger = logging.getLogger("app.routers.health")

router = APIRouter(tags=["health"])

http_client: httpx.AsyncClient | None = None


async def get_http_client() -> httpx.AsyncClient:
    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=1.5)
    return http_client


async def _run_health_checks() -> bool:
    if os.getenv("BYPASS_HEALTH_CHECKS") == "1":
        logger.warning("BYPASS_HEALTH_CHECKS is active. Skipping all service health checks.")
        return True

    checks: dict[str, bool | str] = {}

    async def _check(name: str, coro, timeout: float = 1.0):
        try:
            await asyncio.wait_for(coro, timeout=timeout)
            checks[name] = True
        except asyncio.TimeoutError:
            checks[name] = f"timeout ({timeout}s)"
        except Exception as e:
            checks[name] = repr(e)

    async def _check_redis():
        try:
            from app.services.redis import redis_service
            await redis_service.client.ping()
            checks["redis"] = True
        except Exception as e:
            checks["redis"] = str(e)

    async def _check_postgres():
        import asyncpg
        conn = None
        try:
            conn = await asyncpg.connect(settings.postgres_dsn, timeout=3.0)
            await conn.execute("SELECT 1")
            checks["postgres"] = True
        except Exception as e:
            checks["postgres"] = str(e)
        finally:
            if conn:
                await conn.close()

    async def _check_stt():
        key = os.getenv("DEEPGRAM_API_KEY")
        if not key:
            checks["stt_deepgram"] = "DEEPGRAM_API_KEY not set"
            return
        try:
            client = httpx.AsyncClient(timeout=2.0)
            resp = await client.get("https://api.deepgram.com/v1/projects", headers={"Authorization": f"Token {key}"})
            checks["stt_deepgram"] = resp.is_success
            await client.aclose()
        except Exception as e:
            checks["stt_deepgram"] = str(e)

    async def _check_tts():
        key = os.getenv("CARTESIA_API_KEY")
        if not key:
            checks["tts_cartesia"] = "CARTESIA_API_KEY not set"
            return
        try:
            client = httpx.AsyncClient(timeout=2.0)
            resp = await client.get("https://api.cartesia.ai")
            checks["tts_cartesia"] = resp.is_success
            await client.aclose()
        except Exception as e:
            checks["tts_cartesia"] = str(e)

    async def _check_mantraassist_backend():
        url = os.getenv("MANTRAASSIST_BACKEND_URL", "").rstrip("/")
        if not url:
            checks["mantraassist_backend"] = "MANTRAASSIST_BACKEND_URL not set"
            return
        try:
            client = await get_http_client()
            resp = await client.get(f"{url}/api/v1/health")
            if resp.is_success:
                data = resp.json()
                checks["mantraassist_backend"] = data.get("data", {}).get("success") is True
            else:
                checks["mantraassist_backend"] = f"HTTP {resp.status_code}"
        except Exception as e:
            checks["mantraassist_backend"] = str(e)

    async def _check_s3():
        bucket = settings.s3_bucket
        if not bucket:
            checks["s3"] = "AWS_S3_BUCKET_NAME not set"
            return
        try:
            loop = asyncio.get_running_loop()
            await asyncio.wait_for(
                loop.run_in_executor(None, _check_s3_bucket, bucket),
                timeout=1.0,
            )
            checks["s3"] = True
        except Exception as e:
            checks["s3"] = str(e)

    await asyncio.gather(
        _check("livekit", livekit_service.lk.room.list_rooms(api.ListRoomsRequest()), timeout=1.0),
        _check_redis(),
        _check_postgres(),
        _check_stt(),
        _check_tts(),
        _check_mantraassist_backend(),
        _check_s3(),
        return_exceptions=True,
    )

    all_ok = True
    for service, status in checks.items():
        if status is True:
            logger.info("  - Healthcheck OK: %s", service)
        else:
            all_ok = False
            logger.warning("  - Healthcheck FAILED: %s -> %s", service, status)

    return all_ok


def _check_s3_bucket(bucket: str):
    _saved = {}
    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION", "AWS_REGION"):
        _saved[var] = os.environ.get(var)
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ.pop(var, None)
    try:
        s3 = boto3.client("s3")
        s3.head_bucket(Bucket=bucket)
    finally:
        for var, val in _saved.items():
            if val is not None:
                os.environ[var] = val
            else:
                os.environ.pop(var, None)


@router.get("/health")
async def health_check():
    healthy = await _run_health_checks()
    return JSONResponse(content={"healthy": healthy})
