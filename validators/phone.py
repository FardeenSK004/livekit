"""Phone number validation."""

import re


def is_valid_phone(phone_num: str) -> bool:
    if not phone_num:
        return False
    clean = re.sub(r"[^\d+]", "", phone_num)
    return len(clean) >= 10
