"""TOS Telemetry service — reports call lifecycle events to TOS endpoint."""

from __future__ import annotations

import json
import logging
import os

import httpx

logger = logging.getLogger("app.services.telemetry")


async def report_telemetry(
    tos_task_id: str,
    message: str,
    call_id: str | None = None,
    level: str = "info",
    tos_token: str | None = None,
    data: dict | None = None,
) -> bool:
    tos_url = os.getenv("TOS_ENDPOINT", "").rstrip("/")
    if not tos_url:
        logger.error("TOS_ENDPOINT environment variable not set. Cannot send telemetry.")
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
            if not resp.is_success:
                logger.warning(
                    "TOS telemetry failed with status %s for task %s.",
                    resp.status_code,
                    tos_task_id,
                )
                return False
            return True
    except httpx.RequestError as e:
        logger.error(
            "TOS telemetry request error for task %s: %s", tos_task_id, e
        )
        return False
    except Exception as e:
        logger.error(
            "TOS telemetry error for task %s: %s", tos_task_id, e, exc_info=True
        )
        return False
