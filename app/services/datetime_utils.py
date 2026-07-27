"""Datetime helpers for webhook payloads."""

from __future__ import annotations

import datetime
from typing import Optional


def normalize_to_iso8601(dt_str: Optional[str]) -> Optional[str]:
    """Convert 'YYYY-MM-DD HH:MM:SS' to local ISO-8601 'YYYY-MM-DDTHH:MM:SS' (no offset).

    Returns None if input is None/empty. Passes through unparseable strings unchanged.
    """
    if not dt_str:
        return None
    try:
        dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
    except (ValueError, TypeError):
        return dt_str
