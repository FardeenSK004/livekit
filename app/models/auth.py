"""Authentication models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    token: str
    expires_in: int = 86400  # 24h


class TokenPayload(BaseModel):
    sub: str = ""
    exp: float = 0.0
    iat: float = 0.0
