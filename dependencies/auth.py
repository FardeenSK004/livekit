"""Authentication dependency and token verification."""

import os
from typing import Annotated, Dict, Any
from fastapi import HTTPException, Request, Depends
import jwt

JWT_SECRET = os.getenv("JWT_SECRET", "secret")
JWT_ALGORITHM = "HS256"


def require_auth(request: Request) -> Dict[str, Any]:
    """Dependency to protect routes via JWT Bearer token."""
    auth = request.headers.get("Authorization", "")
    token = None
    if auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1]
    else:
        token = request.query_params.get("token")

    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        request.state.user = payload
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


AuthUser = Annotated[Dict[str, Any], Depends(require_auth)]

__all__ = ["require_auth", "AuthUser", "JWT_SECRET", "JWT_ALGORITHM"]
