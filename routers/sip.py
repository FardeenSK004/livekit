"""SIP Trunks and Dispatch Rules routes."""

from fastapi import APIRouter, Request
from controllers.sip import sip_controller

router = APIRouter(tags=["SIP"])


@router.post("/api/v1/sip/trunks/inbound")
async def create_inbound_trunk(request: Request):
    """Create a new SIP Inbound Trunk."""
    return await sip_controller.create_inbound_trunk(request)


@router.post("/api/v1/sip/trunks/inbound/voicelink")
async def create_voicelink_inbound_trunk(request: Request):
    """Create a VoiceLink SIP Inbound Trunk."""
    return await sip_controller.create_voicelink_inbound_trunk(request)


@router.get("/api/v1/sip/trunks/inbound")
async def list_sip_inbound_trunks(request: Request):
    """List all SIP Inbound Trunks."""
    return await sip_controller.list_sip_inbound_trunks(request)


@router.delete("/api/v1/sip/trunks/inbound/{trunk_id}")
async def delete_sip_inbound_trunk(trunk_id: str, request: Request):
    """Delete a SIP Inbound Trunk."""
    return await sip_controller.delete_sip_inbound_trunk(trunk_id, request)


@router.patch("/api/v1/sip/trunks/inbound/{trunk_id}")
async def update_inbound_sip_trunk(trunk_id: str, request: Request):
    """Update fields on an inbound trunk."""
    return await sip_controller.update_inbound_sip_trunk(trunk_id, request)


@router.post("/api/v1/sip/dispatch-rules")
async def create_dispatch_rule(request: Request):
    """Create a SIP Dispatch Rule."""
    return await sip_controller.create_dispatch_rule(request)


@router.get("/api/v1/sip/dispatch-rules")
async def list_dispatch_rules(request: Request):
    """List all SIP Dispatch Rules."""
    return await sip_controller.list_dispatch_rules(request)


@router.delete("/api/v1/sip/dispatch-rules/{rule_id}")
async def delete_dispatch_rule(rule_id: str, request: Request):
    """Delete a SIP Dispatch Rule."""
    return await sip_controller.delete_dispatch_rule(rule_id, request)


@router.patch("/api/v1/sip/dispatch-rules/{rule_id}")
async def update_sip_dispatch_rule(rule_id: str, request: Request):
    """Update a SIP Dispatch Rule."""
    return await sip_controller.update_sip_dispatch_rule(rule_id, request)


@router.get("/api/v1/sip/plivo-xml")
@router.post("/api/v1/sip/plivo-xml")
async def plivo_xml(request: Request):
    """Plivo XML handler."""
    return await sip_controller.plivo_xml(request)


@router.get("/api/v1/sip/twilio-webhook")
@router.post("/api/v1/sip/twilio-webhook")
async def twilio_webhook(request: Request):
    """Twilio TwiML webhook handler."""
    return await sip_controller.twilio_webhook(request)


@router.post("/api/v1/sip/plivo-dial-status")
async def plivo_dial_status(request: Request):
    """Plivo dial status callback."""
    return await sip_controller.plivo_dial_status(request)


@router.post("/api/v1/sip/inbound/setup")
async def setup_inbound_sip(request: Request):
    """One-click inbound SIP setup."""
    return await sip_controller.setup_inbound_sip(request)


@router.post("/api/v1/sip/trunks/outbound")
@router.post("/api/v1/sip/trunks/outbound/zadarma")
async def create_zadarma_sip_trunk(request: Request):
    """Create a Zadarma SIP trunk."""
    return await sip_controller.create_zadarma_sip_trunk(request)


@router.post("/api/v1/sip/trunks/outbound/twilio")
async def create_twilio_sip_trunk(request: Request):
    """Create a Twilio SIP trunk."""
    return await sip_controller.create_twilio_sip_trunk(request)


@router.post("/api/v1/sip/trunks/outbound/voice_link")
async def create_voicelink_sip_trunk(request: Request):
    """Create a VoiceLink SIP trunk."""
    return await sip_controller.create_voicelink_sip_trunk(request)


@router.post("/api/v1/sip/trunks/outbound/plivo")
async def create_and_call_plivo(request: Request):
    """Create Plivo trunk and call."""
    return await sip_controller.create_and_call_plivo(request)


@router.get("/api/v1/sip/trunks/outbound")
async def list_sip_outbound_trunks(request: Request):
    """List all SIP outbound trunks."""
    return await sip_controller.list_sip_outbound_trunks(request)


@router.delete("/api/v1/sip/trunks/outbound/{trunk_id}")
async def delete_sip_outbound_trunk(trunk_id: str, request: Request):
    """Delete a SIP outbound trunk."""
    return await sip_controller.delete_sip_outbound_trunk(trunk_id, request)
