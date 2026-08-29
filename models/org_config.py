"""Organisation configuration models."""

from typing import Any, Dict, List, Optional
from models.base import BaseSchema


class OrgConfig(BaseSchema):
    """Organisation configuration mapped to a phone number."""

    phone_number: str
    org_id: str
    kb_tags: List[str] = []
    prompt: Optional[str] = None
    voice: Optional[str] = None
    model: Optional[str] = None
    transfer_numbers: Dict[str, str] = {}
    client_name: Optional[str] = None
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
