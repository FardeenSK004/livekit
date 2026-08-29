"""General purpose utilities."""

import re


def sanitize_filename(filename: str) -> str:
    """Sanitize string for safe filenames."""
    return re.sub(r"[^\w\-_.]", "_", filename)
