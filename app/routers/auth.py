from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.config.constants import JWT_EXPIRY_HOURS
from app.models.auth import LoginRequest
from app.services.auth import auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login")
async def login(body: LoginRequest):
    if not settings.ADMIN_USERNAME_HASH or not settings.ADMIN_PASSWORD_HASH:
        raise HTTPException(status_code=500, detail="Auth not configured")
    if not auth_service.verify_login(body.username, body.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = auth_service.create_token(body.username)
    return {
        "token": token,
        "expires_in": JWT_EXPIRY_HOURS * 3600,
        "username": body.username,
    }


def require_auth(request: Request):
    auth_service.require_auth(request)
