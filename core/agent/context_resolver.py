"""Context and phone number resolution for inbound and outbound calls."""

import os
import json
import logging
import aiohttp
import asyncio
from typing import Optional, Dict, Any, List

from core.kb.knowledge_base import PostgresKnowledgeBase
from dependencies.database import get_db_connection

logger = logging.getLogger("core.agent.context_resolver")

_GLOBAL_KB: Optional[PostgresKnowledgeBase] = None


def get_global_kb() -> PostgresKnowledgeBase:
    """Return shared singleton PostgresKnowledgeBase."""
    global _GLOBAL_KB
    if _GLOBAL_KB is None:
        dsn = (
            f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
            f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
        )
        _GLOBAL_KB = PostgresKnowledgeBase(dsn)
    return _GLOBAL_KB


async def resolve_from_db(phone_number: str) -> Optional[Dict[str, Any]]:
    """Lookup phone configuration from PostgreSQL org_configs table."""
    try:
        clean_number = phone_number.replace("+", "")
        conn = await get_db_connection()
        row = await conn.fetchrow(
            "SELECT * FROM org_configs WHERE phone_number IN ($1, $2) AND is_active = true",
            phone_number,
            clean_number,
        )
        await conn.close()

        if row:
            r = dict(row)
            kb_tags = r.get("kb_tags")
            if isinstance(kb_tags, str):
                try:
                    kb_tags = json.loads(kb_tags)
                except Exception:
                    kb_tags = [t.strip() for t in kb_tags.split(",") if t.strip()]

            transfer_numbers = r.get("transfer_numbers")
            if isinstance(transfer_numbers, str):
                try:
                    transfer_numbers = json.loads(transfer_numbers)
                except Exception:
                    transfer_numbers = {}

            org_id = r.get("org_id")
            kb_ids = []
            if org_id:
                try:
                    kb = get_global_kb()
                    kb_ids = await kb.get_kb_ids_for_org(org_id)
                except Exception as e:
                    logger.warning(f"Failed to lookup dynamic kb_ids for org {org_id}: {e}")
                    kb_ids = [str(org_id)]

            return {
                "org_id": org_id,
                "kb_ids": kb_ids,
                "kb_tags": kb_tags or [],
                "prompt": r.get("prompt"),
                "voice": r.get("voice"),
                "model": r.get("model"),
                "process_id": r.get("process_id"),
                "transfer_numbers": transfer_numbers or {},
                "client_name": r.get("client_name"),
            }
        return None
    except Exception as e:
        logger.error(f"Failed to query DB for phone number {phone_number}: {e}")
        return None


async def resolve_from_mantra_backend(phone_number: str) -> Optional[Dict[str, Any]]:
    """Call MantraAssist backend to resolve inbound call context from dialed phone number."""
    base_url = os.getenv("MANTRAASSIST_BACKEND_URL", "").rstrip("/")
    if not base_url:
        return None

    url = f"{base_url}/api/v1/telephony/resolve-inbound-call"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json={"phone_number": phone_number},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data
                return None
    except Exception as e:
        logger.error(f"Failed to resolve inbound call context: {e}")
        return None


async def resolve_inbound_context(phone_number: str) -> Optional[Dict[str, Any]]:
    """Resolves inbound call context from DB."""
    return await resolve_from_db(phone_number)
