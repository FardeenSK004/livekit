"""Datetime normalization and ISO-8601 formatting."""

import datetime
from typing import Optional


def normalize_datetime(dt_str: Optional[str]) -> Optional[str]:
    """Normalize any datetime string into standard ISO-8601 UTC string (YYYY-MM-DDTHH:MM:SSZ)."""
    if not dt_str:
        return None
    cleaned = str(dt_str).strip()
    if not cleaned or cleaned.lower() in ("none", "null"):
        return None

    # Replace local space format with T
    if " " in cleaned and "T" not in cleaned:
        cleaned = cleaned.replace(" ", "T")

    # If it ends with Z or +00:00, parse and ensure clean format
    try:
        if cleaned.endswith("Z"):
            dt = datetime.datetime.fromisoformat(cleaned[:-1])
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        elif "+" in cleaned or "-" in cleaned[10:]:
            dt = datetime.datetime.fromisoformat(cleaned)
            utc_dt = dt.astimezone(datetime.timezone.utc)
            return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            dt = datetime.datetime.fromisoformat(cleaned)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        # Return cleaned as fallback
        return cleaned
