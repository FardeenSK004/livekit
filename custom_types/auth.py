"""Authentication type definitions."""

from typing import Optional
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    expires_in: int
    username: str


class TokenPayload(BaseModel):
    sub: str
    exp: int
    iat: int
