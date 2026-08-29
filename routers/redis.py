"""Redis inspector endpoints."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/redis", tags=["Redis"])


@router.get("/info")
async def redis_info(request: Request):
    redis_client = getattr(request.app.state, "redis_client", None)
    if not redis_client:
        return JSONResponse({"error": "Redis not connected"}, status_code=500)
    info = await redis_client.info()
    return {"status": "success", "info": info}


@router.get("/queue")
async def redis_queue(request: Request):
    redis_client = getattr(request.app.state, "redis_client", None)
    if not redis_client:
        return JSONResponse({"error": "Redis not connected"}, status_code=500)
    items = await redis_client.zrange("queue:pending", 0, -1, withscores=True)
    return {"status": "success", "count": len(items), "queue": items}


@router.get("/active-details")
async def redis_active_details(request: Request):
    redis_client = getattr(request.app.state, "redis_client", None)
    if not redis_client:
        return JSONResponse({"error": "Redis not connected"}, status_code=500)
    active = await redis_client.hgetall("calls:active")
    return {"status": "success", "active_calls": active}


@router.get("/keys")
async def redis_keys(request: Request, pattern: str = "*", limit: int = 100):
    redis_client = getattr(request.app.state, "redis_client", None)
    if not redis_client:
        return JSONResponse({"error": "Redis not connected"}, status_code=500)
    keys = await redis_client.keys(pattern)
    return {"status": "success", "count": len(keys[:limit]), "keys": keys[:limit]}


@router.get("/key-detail")
async def redis_key_detail(request: Request, key: str):
    redis_client = getattr(request.app.state, "redis_client", None)
    if not redis_client:
        return JSONResponse({"error": "Redis not connected"}, status_code=500)
    k_type = await redis_client.type(key)
    val = None
    if k_type == "string":
        val = await redis_client.get(key)
    elif k_type == "hash":
        val = await redis_client.hgetall(key)
    elif k_type == "zset":
        val = await redis_client.zrange(key, 0, -1, withscores=True)
    elif k_type == "list":
        val = await redis_client.lrange(key, 0, -1)
    elif k_type == "set":
        val = list(await redis_client.smembers(key))
    return {"key": key, "type": k_type, "value": val}


@router.delete("/key")
async def redis_delete_key(request: Request, key: str):
    redis_client = getattr(request.app.state, "redis_client", None)
    if not redis_client:
        return JSONResponse({"error": "Redis not connected"}, status_code=500)
    deleted = await redis_client.delete(key)
    return {"status": "success", "deleted": deleted}
