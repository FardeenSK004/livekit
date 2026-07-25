"""Webhook HMAC signing parity tests."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.webhook import WebhookService


@pytest.mark.asyncio
async def test_webhook_sign_order_matches_mantra():
    svc = WebhookService()
    payload = {"event": "CALL_DATA_UPDATE", "call_id": "abc"}
    body = json.dumps(payload, separators=(",", ":"))

    captured = {}

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, content=None, headers=None):
            captured["url"] = url
            captured["content"] = content
            captured["headers"] = headers
            return FakeResp()

    with patch("app.services.webhook.settings") as settings:
        settings.MANTRAASSIST_BACKEND_URL = "https://example.com"
        settings.MANTRAASSIST_WEBHOOK_SECRET = "secret"
        with patch("app.services.webhook.httpx.AsyncClient", return_value=FakeClient()):
            ok = await svc.send(payload)

    assert ok is True
    assert captured["content"] == body
    assert captured["headers"]["x-source"] == "n8n"
    ts = captured["headers"]["x-timestamp"]
    expected = hmac.new(
        b"secret", f"{body}.{ts}".encode(), hashlib.sha256
    ).hexdigest()
    assert captured["headers"]["x-signature"] == expected
