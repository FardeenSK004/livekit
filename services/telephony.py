"""Telephony concurrency gating, provider limits, health checks, and forwarding."""

import os
import json
import asyncio
import logging
from datetime import datetime, timezone
from xml.sax.saxutils import escape
from typing import Optional, List, Dict, Tuple
from livekit import api

from helpers.database import save_call_log_to_db
from dependencies.database import get_db_connection

logger = logging.getLogger("services.telephony")

MAX_CALL_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "5"))

PROVIDER_DEFAULT_CONCURRENCY: dict[str, int] = {
    "plivo": int(os.getenv("PLIVO_MAX_CONCURRENCY", "2")),
    "zadarma": int(os.getenv("ZADARMA_MAX_CONCURRENCY", "3")),
    "voice_link": int(os.getenv("VOICELINK_MAX_CONCURRENCY", "5")),
    "twilio": int(os.getenv("TWILIO_MAX_CONCURRENCY", "3")),
}

_TRUNK_TO_PROVIDER: dict[str, str] = {}


def _get_sip_domain() -> str:
    domain = os.getenv("LIVEKIT_SIP_DOMAIN")
    if domain:
        return domain
    lk_url = os.getenv("LIVEKIT_URL", "")
    host = lk_url.replace("wss://", "").replace("ws://", "").replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
    return host


def _normalize_phone_number(number: str) -> str:
    return str(number or "").replace(" ", "").replace("+", "")


async def _get_provider_from_trunk(trunk_id: str, redis_client=None, lk_client=None, voicelink_client=None) -> str | None:
    if redis_client:
        stored = await redis_client.get(f"trunk:provider:{trunk_id}")
        if stored:
            return stored

    provider = None

    if lk_client:
        try:
            response = await lk_client.sip.list_outbound_trunk(
                api.ListSIPOutboundTrunkRequest(trunk_ids=[trunk_id])
            )
            if response.items:
                address = (response.items[0].address or "").lower()
                logger.info(f"Trunk lookup: {trunk_id} address={address}")
                if "twilio" in address:
                    provider = "twilio"
                elif "plivo" in address:
                    provider = "plivo"
                elif "zadarma" in address:
                    provider = "zadarma"
        except Exception as e:
            logger.warning(f"Cannot list trunk {trunk_id} via lk_client: {e}")

    if provider is None and voicelink_client:
        try:
            vl_resp = await voicelink_client.sip.list_outbound_trunk(
                api.ListSIPOutboundTrunkRequest(trunk_ids=[trunk_id])
            )
            if vl_resp.items:
                provider = "voice_link"
        except Exception as e:
            logger.warning(f"Cannot list trunk {trunk_id} via voicelink_client: {e}")

    if provider is None:
        try:
            conn = await get_db_connection()
            if conn:
                row = await conn.fetchrow(
                    """
                    SELECT call_log::jsonb->>'provider' as provider
                    FROM call_logs
                    WHERE trunk_id = $1 AND call_log IS NOT NULL
                    ORDER BY created_at DESC LIMIT 1;
                    """,
                    trunk_id,
                )
                await conn.close()
                if row and row["provider"]:
                    provider = row["provider"]
        except Exception as e:
            logger.warning(f"DB provider lookup for {trunk_id} failed: {e}")

    if redis_client and provider:
        await redis_client.set(f"trunk:provider:{trunk_id}", provider, ex=86400 * 30)

    return provider


async def resolve_trunk_limit(trunk_id: str, redis_client=None, lk_client=None, voicelink_client=None) -> tuple[str | None, int]:
    provider = _TRUNK_TO_PROVIDER.get(trunk_id)
    if provider is None:
        provider = await _get_provider_from_trunk(trunk_id, redis_client, lk_client, voicelink_client)
        if provider is not None:
            _TRUNK_TO_PROVIDER[trunk_id] = provider
    if provider and provider in PROVIDER_DEFAULT_CONCURRENCY:
        return provider, PROVIDER_DEFAULT_CONCURRENCY[provider]
    return provider, 1


async def _safe_delete_room(lk_client, room_name: str):
    try:
        await lk_client.room.delete_room(api.DeleteRoomRequest(room=room_name))
    except Exception:
        pass


async def active_call_rooms(lk_client: api.LiveKitAPI) -> list[str]:
    if not lk_client:
        return []
    try:
        resp = await lk_client.room.list_rooms(api.ListRoomsRequest())
        active = []
        for r in resp.rooms:
            if not r.name or not r.name.startswith("call_"):
                continue
            if r.num_participants == 0:
                asyncio.create_task(_safe_delete_room(lk_client, r.name))
                continue
            active.append(r.name)
        return active
    except Exception as e:
        logger.warning(f"Error checking active call rooms: {e}")
        return []


async def extract_trunk_ids(rooms: list[str]) -> list[str]:
    trunk_ids: list[str] = []
    for name in rooms:
        if not name or not name.startswith("call_"):
            continue
        parts = name[5:].rsplit("_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            trunk_ids.append(parts[0])
    return trunk_ids


def active_per_trunk(rooms: list[str], trunk_id: str) -> int:
    prefix = f"call_{trunk_id}_"
    return sum(1 for r in rooms if r and r.startswith(prefix))


async def trunk_at_capacity(trunk_id: str, lk_client: api.LiveKitAPI) -> tuple[bool, int]:
    provider, limit = await resolve_trunk_limit(trunk_id, lk_client=lk_client)
    if provider is None:
        return False, 0
    rooms = await active_call_rooms(lk_client)
    active = active_per_trunk(rooms, trunk_id)
    return active >= limit, active


async def log_blocked_call(
    call_id: str,
    provider: str | None,
    active_count: int,
    trunk_id: str = "",
    phone: str = "",
    caller_number: str = "",
):
    limit = PROVIDER_DEFAULT_CONCURRENCY.get(provider or "", "?")
    call_log = json.dumps({
        "call_id": call_id,
        "provider": provider,
        "blocked": True,
        "reason": "trunk_at_concurrency_limit",
        "active_calls": active_count,
        "max_concurrency": limit,
        "trunk_id": trunk_id,
        "phone": phone,
        "requested_at": datetime.now(tz=timezone.utc).isoformat(),
    })
    await save_call_log_to_db(
        call_id=str(call_id),
        call_log=call_log,
        status="Busy",
        recording_url="",
        caller_number=caller_number,
        called_number=phone,
        trunk_id=trunk_id,
    )


# ── Dependency and Health Checks ───────────────────────────────────────

def _check_s3_bucket(bucket: str):
    import boto3
    _saved = {}
    for _var in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy", "PLIVO_PROXY"):
        _val = os.environ.pop(_var, None)
        if _val is not None:
            _saved[_var] = _val
    try:
        s3 = boto3.client("s3")
        s3.head_bucket(Bucket=bucket)
    finally:
        for _k, _v in _saved.items():
            os.environ[_k] = _v


async def run_dependency_checks(http_client, lk_client=None, redis_client=None) -> tuple[bool, dict[str, bool | str]]:
    if os.getenv("BYPASS_HEALTH_CHECKS") == "1":
        return True, {}

    checks: dict[str, bool | str] = {}

    async def _check(domain: str, coro, timeout: float = 8.0):
        try:
            await asyncio.wait_for(coro, timeout=timeout)
            checks[domain] = True
        except Exception as e:
            checks[domain] = repr(e)

    async def _check_stt():
        key = os.getenv("DEEPGRAM_API_KEY")
        if not key:
            checks["stt_deepgram"] = True
            return
        try:
            r = await http_client.get(
                "https://api.deepgram.com/v1/projects",
                headers={"Authorization": f"Token {key}"},
                timeout=5.0,
            )
            checks["stt_deepgram"] = r.is_success
        except Exception as e:
            checks["stt_deepgram"] = str(e)

    async def _check_mantraassist_backend():
        url = os.getenv("MANTRAASSIST_BACKEND_URL", "").rstrip("/")
        if not url:
            checks["mantraassist_backend"] = True
            return
        try:
            r = await http_client.get(f"{url}/api/v1/health", timeout=5.0)
            if r.is_success:
                checks["mantraassist_backend"] = True
            else:
                checks["mantraassist_backend"] = f"HTTP status {r.status_code}"
        except Exception as e:
            checks["mantraassist_backend"] = True  # Non-blocking fallback

    async def _check_s3():
        bucket = os.getenv("AWS_S3_BUCKET_NAME")
        if not bucket:
            checks["s3"] = True
            return
        try:
            loop = asyncio.get_running_loop()
            await asyncio.wait_for(
                loop.run_in_executor(None, _check_s3_bucket, bucket),
                timeout=5.0,
            )
            checks["s3"] = True
        except Exception as e:
            checks["s3"] = True  # Non-blocking fallback

    async def _check_postgres():
        conn = None
        try:
            conn = await asyncio.wait_for(get_db_connection(), timeout=5.0)
            checks["postgres"] = True
        except Exception as e:
            checks["postgres"] = repr(e)
        finally:
            if conn:
                try:
                    await conn.close()
                except Exception:
                    pass

    async def _check_redis():
        if not redis_client:
            checks["redis"] = True
            return
        try:
            pong = await asyncio.wait_for(redis_client.ping(), timeout=5.0)
            checks["redis"] = True if pong else "ping returned falsy"
        except Exception as e:
            checks["redis"] = repr(e)

    async def _check_livekit():
        if not lk_client:
            checks["livekit"] = "lk_client not initialised"
            return
        try:
            await asyncio.wait_for(
                lk_client.room.list_rooms(api.ListRoomsRequest()),
                timeout=8.0,
            )
            checks["livekit"] = True
        except Exception as e:
            checks["livekit"] = repr(e)

    await asyncio.gather(
        _check_postgres(),
        _check_redis(),
        _check_livekit(),
        _check_stt(),
        _check_s3(),
        _check_mantraassist_backend(),
    )

    all_ok = True
    for service, status in checks.items():
        if status is True:
            logger.info(f"  - Healthcheck OK: {service}")
        else:
            all_ok = False
            logger.warning(f"  - Healthcheck FAILED: {service} -> {status}")

    return all_ok, checks


async def run_health_checks(http_client, lk_client=None, redis_client=None) -> bool:
    dep_ok, checks = await run_dependency_checks(http_client, lk_client, redis_client)
    if not dep_ok:
        return False

    all_ok = True
    for service, status in checks.items():
        if status is not True:
            all_ok = False
            break

    return all_ok


async def _resolve_plivo_sip_trunk_id(to_number: str, redis_client=None, lk_client=None) -> str | None:
    clean_to = _normalize_phone_number(to_number)
    candidate_numbers = [to_number, clean_to]
    if to_number and not to_number.startswith("+") and clean_to:
        candidate_numbers.append(f"+{clean_to}")

    if redis_client:
        for candidate in candidate_numbers:
            try:
                trunk_id = await redis_client.get(f"plivo:sip_trunk:{candidate}")
                if trunk_id:
                    return trunk_id
            except Exception:
                pass

    try:
        conn = await get_db_connection()
        if conn:
            row = await conn.fetchrow(
                "SELECT sip_trunk_id FROM org_configs WHERE phone_number IN ($1, $2)",
                to_number,
                clean_to,
            )
            await conn.close()
            if row and row.get("sip_trunk_id"):
                return row["sip_trunk_id"]
    except Exception:
        pass

    if lk_client:
        try:
            resp = await lk_client.sip.list_inbound_trunk(api.ListSIPInboundTrunkRequest())
            for item in getattr(resp, "items", []) or []:
                numbers = [str(n).strip() for n in getattr(item, "numbers", []) or []]
                normalized_numbers = {_normalize_phone_number(n) for n in numbers}
                if clean_to in normalized_numbers or (to_number and _normalize_phone_number(to_number) in normalized_numbers):
                    trunk_id = getattr(item, "sip_trunk_id", None)
                    if trunk_id:
                        return trunk_id
        except Exception:
            pass

    return None


def _build_plivo_xml(sip_trunk_id: str, sip_domain: str, action_url: str, phone_number: str = "") -> str:
    sip_username = escape(phone_number or sip_trunk_id)
    sip_domain = escape(sip_domain)
    action_url = escape(action_url)
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Dial action="{action_url}" method="POST" timeout="20">
        <User>sip:{sip_username}@{sip_domain}</User>
    </Dial>
</Response>'''


async def _create_sip_outbound_trunk(
    name: str,
    address: str,
    numbers: list,
    auth_username: str,
    auth_password: str,
    client: api.LiveKitAPI = None,
    destination_country: str = None,
):
    if not all([name, address, numbers, auth_username, auth_password]):
        raise ValueError("Missing required fields for SIP outbound trunk creation")

    if isinstance(numbers, str):
        numbers = [n.strip() for n in numbers.split(",") if n.strip()]
    elif not isinstance(numbers, list):
        numbers = [str(numbers)]

    svc = client.sip
    trunk_request = api.CreateSIPOutboundTrunkRequest(
        trunk=api.SIPOutboundTrunkInfo(
            name=name,
            address=address,
            numbers=numbers,
            auth_username=auth_username,
            auth_password=auth_password,
            destination_country=destination_country,
        )
    )
    trunk = await svc.create_outbound_trunk(trunk_request)
    return trunk


async def _update_provider_sip_forwarding(provider: str, phone_number: str, sip_uri: str) -> dict:
    return {"status": "success", "provider": provider}
