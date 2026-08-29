"""Phone number parsing and E.164 normalization."""


def format_e164_phone_number(phone_num: str, country_code: str = "") -> str:
    """Format phone number to standard E.164 with leading + sign and country code."""
    if not phone_num:
        return ""
    num = str(phone_num).strip()
    if not num:
        return ""
    if num.startswith("+"):
        return num

    clean = "".join([c for c in num if c.isdigit()])
    if not clean:
        return num

    cc = "".join([c for c in str(country_code) if c.isdigit()]) if country_code else ""

    if cc and clean.startswith(cc) and len(clean) > len(cc):
        return f"+{clean}"
    elif len(clean) == 10 and cc:
        return f"+{cc}{clean}"
    elif len(clean) == 10 and not cc:
        return f"+91{clean}"
    else:
        return f"+{clean}"
