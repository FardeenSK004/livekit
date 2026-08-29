"""Organisation configuration routes."""

from fastapi import APIRouter, Request
from controllers.org_configs import org_configs_controller

router = APIRouter(prefix="/api/v1/org-configs", tags=["Org Configs"])


@router.get("")
async def list_org_configs(request: Request):
    """List all org configs, optionally filtered by org_id."""
    org_id = request.query_params.get("org_id")
    return await org_configs_controller.list_org_configs(org_id)


@router.get("/{phone_number}")
async def get_org_config(phone_number: str):
    """Get a specific org config by phone number."""
    return await org_configs_controller.get_org_config(phone_number)


@router.put("/{phone_number}")
async def update_org_config(phone_number: str, request: Request):
    """Update fields on an existing org config."""
    payload = await request.json()
    return await org_configs_controller.update_org_config(phone_number, payload)


@router.delete("/{phone_number}")
async def delete_org_config(phone_number: str):
    """Soft delete an org config by setting is_active = false."""
    return await org_configs_controller.delete_org_config(phone_number)
