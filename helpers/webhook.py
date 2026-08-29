"""HMAC-signed webhook dispatcher to MantraAssist backend."""

import asyncio
import datetime
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Optional
import httpx
from helpers.database import save_call_log_to_db

logger = logging.getLogger("mantra.helpers.webhook")


async def _claim_backend_delivery(dedupe_key: str, force: bool = False) -> bool:
    """First writer wins per dedupe_key (call_id + ai_call_id) via Redis lock."""
    if not dedupe_key:
        return True
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return True
    try:
        import redis.asyncio as redis

        client = redis.from_url(redis_url, decode_responses=True)
        try:
            if force:
                await client.delete(f"backend_sent:{dedupe_key}")
            claimed = await client.set(f"backend_sent:{dedupe_key}", "1", nx=True, ex=300)
            if not claimed and not force:
                logger.info(
                    f"Backend webhook already claimed for dedupe_key={dedupe_key} — skipping duplicate"
                )
            return bool(claimed) or force
        finally:
            await client.aclose()
    except Exception as e:
        logger.warning(f"backend delivery claim failed for dedupe_key={dedupe_key}, allowing send: {e}")
        return True


async def _release_backend_delivery(dedupe_key: str) -> None:
    """Allow a retry if the claimed delivery failed."""
    if not dedupe_key:
        return
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return
    try:
        import redis.asyncio as redis

        client = redis.from_url(redis_url, decode_responses=True)
        try:
            await client.delete(f"backend_sent:{dedupe_key}")
        finally:
            await client.aclose()
    except Exception as e:
        logger.warning(f"backend delivery release failed for dedupe_key={dedupe_key}: {e}")


async def send_to_backend(payload: dict, max_retries: int = 3, force: bool = False) -> bool:
    """POST post-call payload to MantraAssist backend with HMAC-SHA256 signing."""
    base_url = os.getenv("MANTRAASSIST_BACKEND_URL", "").rstrip("/")
    webhook_secret = os.getenv("MANTRAASSIST_WEBHOOK_SECRET", "")

    if not base_url:
        logger.warning("MANTRAASSIST_BACKEND_URL not set — skipping backend webhook")
        return False

    call_id = ""
    ai_call_id = ""
    event_type = ""
    try:
        if isinstance(payload, dict):
            event_type = payload.get("event", "")
            data = payload.get("data")
            if isinstance(data, dict):
                call_id = str(data.get("call_id") or "")
                ai_call_id = str(data.get("ai_call_id") or "")
    except Exception:
        call_id = ""

    dedupe_key = f"{call_id}_{ai_call_id}" if (call_id and ai_call_id) else call_id
    is_retry_payload = force or (event_type in ("CALL_RETRY", "call_retry"))

    if not await _claim_backend_delivery(dedupe_key, force=is_retry_payload):
        return True

    url = f"{base_url}/api/v1/webhooks/n8n"
    timestamp = str(int(time.time()))
    timestamp_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    payload_str = json.dumps(payload, separators=(',', ':')) if payload else '{}'
    data_to_sign = f"{payload_str}.{timestamp}"

    headers = {
        "Content-Type": "application/json",
        "x-timestamp": timestamp,
        "x-source": "n8n",
        "x-timestamp-iso": timestamp_iso,
    }

    if webhook_secret:
        signature = hmac.new(
            webhook_secret.encode("utf-8"), data_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        headers["x-signature"] = signature

    logger.info(f"Delivering post-call webhook to: {url} call_id={call_id or 'unknown'}")

    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, content=payload_str, headers=headers)
                resp.raise_for_status()
                logger.info(
                    f"Backend webhook delivered successfully (HTTP {resp.status_code}) call_id={call_id or 'unknown'}"
                )

                # Persist delivered payload to PostgreSQL call_logs table
                try:
                    data_obj = payload.get("data") if isinstance(payload, dict) else {}
                    if isinstance(data_obj, dict) and call_id:
                        status_val = str(data_obj.get("call_status") or data_obj.get("status") or "Completed")
                        recording_val = str(data_obj.get("recording_url") or data_obj.get("s3_recording") or "")
                        caller_num = str(data_obj.get("caller_number") or data_obj.get("client_phone") or "")
                        called_num = str(data_obj.get("called_number") or "")
                        trunk_val = str(data_obj.get("trunk_id") or data_obj.get("sip_trunk_id") or "")

                        await save_call_log_to_db(
                            call_id=call_id,
                            call_log=json.dumps(data_obj),
                            status=status_val,
                            recording_url=recording_val,
                            caller_number=caller_num,
                            called_number=called_num,
                            trunk_id=trunk_val,
                        )
                except Exception as db_err:
                    logger.warning(f"Failed to persist delivered payload to DB: {db_err}")

                return True
        except Exception as e:
            logger.error(f"Backend webhook attempt {attempt}/{max_retries} failed: {e}")

        if attempt < max_retries:
            await asyncio.sleep(2 ** (attempt - 1))

    await _release_backend_delivery(dedupe_key)
    return False
