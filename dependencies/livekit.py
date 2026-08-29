"""LiveKit API client dependencies."""

import os
from typing import Annotated, Optional
import aiohttp
from fastapi import Depends, Request
from livekit import api

_lk_client: Optional[api.LiveKitAPI] = None
_plivo_client: Optional[api.LiveKitAPI] = None
_voicelink_client: Optional[api.LiveKitAPI] = None


def get_livekit_client(request: Optional[Request] = None) -> Optional[api.LiveKitAPI]:
    """Get standard LiveKit API client."""
    if request is not None and hasattr(request.app.state, "lk_client"):
        return request.app.state.lk_client

    global _lk_client
    if _lk_client is None:
        api_key = os.getenv("LIVEKIT_API_KEY")
        api_secret = os.getenv("LIVEKIT_API_SECRET")
        lk_url = os.getenv("LIVEKIT_URL")
        if lk_url:
            api_url = (
                lk_url.replace("wss://", "https://")
                if lk_url.startswith("wss://")
                else (
                    lk_url.replace("ws://", "http://")
                    if lk_url.startswith("ws://")
                    else lk_url
                )
            )
            _lk_client = api.LiveKitAPI(url=api_url, api_key=api_key, api_secret=api_secret)
    return _lk_client


def get_plivo_client(request: Optional[Request] = None) -> Optional[api.LiveKitAPI]:
    """Get proxied LiveKit API client for Plivo."""
    if request is not None and hasattr(request.app.state, "plivo_client"):
        return request.app.state.plivo_client
    return get_livekit_client(request)


def get_voicelink_client(request: Optional[Request] = None) -> Optional[api.LiveKitAPI]:
    """Get proxied LiveKit API client for VoiceLink."""
    if request is not None and hasattr(request.app.state, "voicelink_client"):
        return request.app.state.voicelink_client
    return get_livekit_client(request)


LiveKitClientService = Annotated[Optional[api.LiveKitAPI], Depends(get_livekit_client)]

__all__ = ["get_livekit_client", "get_plivo_client", "get_voicelink_client", "LiveKitClientService"]
