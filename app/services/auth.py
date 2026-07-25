"""JWT authentication service."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt as pyjwt
from fastapi import HTTPException, Request

from app.config import settings
from app.config.constants import JWT_ALGORITHM, JWT_EXPIRY_HOURS


class AuthService:
    def verify_login(self, username: str, password: str) -> bool:
        if not settings.ADMIN_USERNAME_HASH or not settings.ADMIN_PASSWORD_HASH:
            return False
        username_hash = hashlib.sha256(username.encode()).hexdigest()
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        return (
            username_hash == settings.ADMIN_USERNAME_HASH
            and password_hash == settings.ADMIN_PASSWORD_HASH
        )

    def create_token(self, username: str = "admin") -> str:
        expiry = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS)
        payload = {
            "sub": username,
            "exp": expiry,
            "iat": datetime.now(timezone.utc),
        }
        return pyjwt.encode(payload, settings.JWT_SECRET, algorithm=JWT_ALGORITHM)

    def verify_token(self, token: str) -> Optional[dict]:
        if not settings.JWT_SECRET:
            return None
        try:
            return pyjwt.decode(
                token, settings.JWT_SECRET, algorithms=[JWT_ALGORITHM]
            )
        except pyjwt.PyJWTError:
            return None

    def require_auth(self, request: Request):
        auth = request.headers.get("Authorization", "")
        token = None
        if auth.startswith("Bearer "):
            token = auth.split(" ", 1)[1]
        else:
            token = request.query_params.get("token")

        if not token:
            raise HTTPException(status_code=401, detail="Missing or invalid token")
        payload = self.verify_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        request.state.user = payload


auth_service = AuthService()
