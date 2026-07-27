"""Calculate next call time with timezone awareness and business hours."""

from __future__ import annotations

import datetime
import logging
from typing import Optional

logger = logging.getLogger("app.services.calculate_call_time")

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def calculate_next_call_on(
    country_iso: Optional[str] = None,
    client_timezone: Optional[str] = None,
    preferred_calling_time: Optional[str] = None,
    skip_off_days: bool = False,
    fallback_hours: int = 24,
) -> str:
    now = datetime.datetime.now()
    if client_timezone:
        try:
            import pytz
            tz = pytz.timezone(client_timezone)
            now = datetime.datetime.now(tz)
        except Exception:
            pass

    if skip_off_days:
        weekday = now.weekday()
        if weekday >= 5:
            days_ahead = 7 - weekday
            now = now + datetime.timedelta(days=days_ahead)
            now = now.replace(hour=9, minute=0, second=0, microsecond=0)
            return now.strftime("%Y-%m-%d %H:%M:%S")

    if preferred_calling_time:
        try:
            parts = preferred_calling_time.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            preferred = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if preferred > now:
                return preferred.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

    next_time = now + datetime.timedelta(hours=fallback_hours)
    return next_time.strftime("%Y-%m-%d %H:%M:%S")
