"""Org config management for MantraAssist."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.services import org_config as org_config_service

router = APIRouter(prefix="/api/v1/org-configs", tags=["org-configs"])


@router.get("")
async def list_org_configs(request: Request):
    org_id = request.query_params.get("org_id")
    try:
        results = await org_config_service.list_org_configs(org_id)
        return {"status": "success", "count": len(results), "org_configs": results}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/{phone_number}")
async def get_org_config(phone_number: str):
    try:
        result = await org_config_service.get_org_config_by_phone(phone_number)
        if not result:
            return JSONResponse(
                {"status_code": 404, "status": "error", "error": "Not found"},
                status_code=404,
            )
        return {"status": "success", "org_config": result}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.put("/{phone_number}")
async def update_org_config(phone_number: str, request: Request):
    payload = await request.json()
    if not payload:
        return JSONResponse({"error": "No payload provided"}, status_code=400)
    try:
        result = await org_config_service.update_org_config(phone_number, payload)
        if result is None:
            return JSONResponse(
                {"status_code": 404, "status": "error", "error": "Not found"},
                status_code=404,
            )
        if isinstance(result, dict) and result.get("message"):
            return {"status": "success", **result}
        return {"status": "success", "org_config": result}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.delete("/{phone_number}")
async def delete_org_config(phone_number: str):
    try:
        ok = await org_config_service.deactivate_org_config(phone_number)
        if not ok:
            return JSONResponse(
                {"status_code": 404, "status": "error", "error": "Not found"},
                status_code=404,
            )
        return {
            "status": "success",
            "message": f"Org config for {phone_number} deactivated",
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
