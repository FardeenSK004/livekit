"""TOS telemetry reporting helper."""

import os
import logging
from typing import Optional, Dict, Any
import httpx

logger = logging.getLogger("helpers.telemetry")


async def report_telemetry(
    tos_task_id: str,
    message: str,
    call_id: Optional[str] = None,
    level: str = "info",
    tos_token: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
) -> bool:
    """Send TOS telemetry events asynchronously to the centralized task orchestrator."""
    tos_url = os.getenv("TOS_ENDPOINT", "").rstrip("/")
    if not tos_url:
        return False

    url = f"{tos_url}/api/telemetry/{tos_task_id}/log"
    token = tos_token or os.getenv("TOS_SERVICE_SECRET", "")

    body = {"level": level, "message": message}
    if call_id:
        body["call_id"] = str(call_id)
    if data:
        body["data"] = data

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(proxy=None, timeout=10.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            return resp.is_success
    except Exception as e:
        logger.debug(f"TOS telemetry request error for task {tos_task_id}: {e}")
        return False
