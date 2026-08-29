"""Telephony and webhook dispatch routes."""

from fastapi import APIRouter, Request
from controllers.telephony import telephony_controller

router = APIRouter(tags=["Telephony"])


@router.post("/api/v1/webhooks/telephony")
async def handle_outbound_call_webhook(request: Request):
    """Webhook handler to process telephony events and trigger outbound agent dispatch."""
    return await telephony_controller.handle_outbound_webhook(request)


@router.post("/dispatch-test")
async def dispatch_test(request: Request):
    """Test endpoint for manual outbound dispatch."""
    return await telephony_controller.dispatch_test(request)


@router.post("/api/v1/test/inbound-call")
async def test_inbound_call(request: Request):
    """Simulate an inbound call dispatch."""
    return await telephony_controller.test_inbound_call(request)
