"""Webhook delivery service — HMAC-signed POST to MantraAssist backend."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger("app.services.webhook")


class WebhookService:
    async def send(
        self,
        payload: dict,
        endpoint: str = "/webhooks/n8n",
        max_retries: int = 3,
    ) -> bool:
        """POST payload with mantra-compatible HMAC signing.

        Sign string: ``{body}.{timestamp}`` (matches mantra.utils.send_to_backend).
        """
        base_url = settings.MANTRAASSIST_BACKEND_URL.rstrip("/")
        if not base_url:
            logger.warning("MANTRAASSIST_BACKEND_URL not set — skipping webhook")
            return False

        url = f"{base_url}{endpoint}"
        timestamp = str(int(time.time()))
        body = json.dumps(payload, separators=(",", ":")) if payload else "{}"
        data_to_sign = f"{body}.{timestamp}"

        headers = {
            "Content-Type": "application/json",
            "x-timestamp": timestamp,
            "x-source": "n8n",
        }

        secret = settings.MANTRAASSIST_WEBHOOK_SECRET
        if secret:
            signature = hmac.new(
                secret.encode("utf-8"),
                data_to_sign.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            headers["x-signature"] = signature
            logger.info("Signing request with HMAC (timestamp: %s)", timestamp)
        else:
            logger.warning(
                "MANTRAASSIST_WEBHOOK_SECRET not set — sending unsigned request"
            )

        logger.info("Delivering webhook to: %s", url)

        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(url, content=body, headers=headers)
                    resp.raise_for_status()
                    logger.info(
                        "Webhook delivered successfully (HTTP %s)", resp.status_code
                    )
                    return True
            except Exception as e:
                logger.error(
                    "Webhook attempt %s/%s failed: %s", attempt, max_retries, e
                )
            if attempt < max_retries:
                await asyncio.sleep(2 ** (attempt - 1))
        return False


webhook_service = WebhookService()
