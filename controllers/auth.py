"""Authentication controller."""

import os
import hashlib
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
import jwt

JWT_SECRET = os.getenv("JWT_SECRET", "secret")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24
ADMIN_USERNAME_HASH = os.getenv("ADMIN_USERNAME_HASH", "")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")


class AuthController:
    """Authentication logic handler."""

    @staticmethod
    def login(username: str, password: str) -> dict:
        username_hash = hashlib.sha256(username.encode()).hexdigest()
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        if not ADMIN_USERNAME_HASH or not ADMIN_PASSWORD_HASH:
            raise HTTPException(status_code=500, detail="Auth not configured")

        if username_hash != ADMIN_USERNAME_HASH or password_hash != ADMIN_PASSWORD_HASH:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        expiry = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS)
        token = jwt.encode(
            {"sub": username, "exp": expiry, "iat": datetime.now(timezone.utc)},
            JWT_SECRET,
            algorithm=JWT_ALGORITHM,
        )

        return {"token": token, "expires_in": JWT_EXPIRY_HOURS * 3600, "username": username}


auth_controller = AuthController()
