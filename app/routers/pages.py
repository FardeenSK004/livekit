"""HTML page routes and frontend config."""

from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(tags=["pages"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATIC_DIR = os.path.join(BASE_DIR, "static")


@router.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "login.html"))


@router.get("/dashboard")
async def dashboard_page():
    return FileResponse(os.path.join(STATIC_DIR, "dashboard.html"))


@router.get("/console")
async def console_page():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@router.get("/network")
async def network_page():
    return FileResponse(os.path.join(STATIC_DIR, "network.html"))


@router.get("/kb-chat")
async def kb_chat_page():
    return FileResponse(os.path.join(STATIC_DIR, "kb_chat.html"))


@router.get("/config")
async def get_config():
    from app.config import settings

    return JSONResponse({"url": settings.LIVEKIT_URL})
