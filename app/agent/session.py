"""Session lifecycle and call-state tracking."""

from __future__ import annotations

import datetime
from typing import Any


class SessionManager:
    """Manages per-call state shared across safety monitors, tools, and finalize."""

    def __init__(self, call_id: str, room_name: str = ""):
        self.call_id = call_id
        self.room_name = room_name
        self.call_state: dict[str, Any] = {
            "user_joined": False,
            "timeline": [
                {
                    "event": "Agent Session Started",
                    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                }
            ],
        }

    @property
    def user_joined(self) -> bool:
        return bool(self.call_state.get("user_joined"))

    @user_joined.setter
    def user_joined(self, value: bool):
        self.call_state["user_joined"] = value

    def append_timeline(self, event: str):
        self.call_state["timeline"].append(
            {
                "event": event,
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            }
        )

    def get(self, key: str, default=None):
        return self.call_state.get(key, default)

    def set(self, key: str, value):
        self.call_state[key] = value
