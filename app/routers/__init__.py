"""HTTP routers for the Mantra UI server."""

from app.routers import auth, dashboard, dispatch, health, kb, org, pages, sip, webhooks

__all__ = [
    "auth",
    "dashboard",
    "dispatch",
    "health",
    "kb",
    "org",
    "pages",
    "sip",
    "webhooks",
]
