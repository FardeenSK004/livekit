"""Authentication and login routes."""

import os
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from controllers.auth import auth_controller

router = APIRouter(tags=["Authentication"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")


@router.get("/")
async def index():
    """Serve the login page."""
    return FileResponse(os.path.join(STATIC_DIR, "login.html"))


@router.post("/api/v1/auth/login")
async def login(request: Request):
    """Authenticate with username/password, return JWT."""
    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")
    return auth_controller.login(username, password)
