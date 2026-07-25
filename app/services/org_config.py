"""Org config database helpers."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from app.services.db import db_service

logger = logging.getLogger("app.services.org_config")


def serialize_org_config(row: dict) -> dict:
    result = dict(row)
    if result.get("created_at"):
        result["created_at"] = result["created_at"].isoformat()
    if result.get("updated_at"):
        result["updated_at"] = result["updated_at"].isoformat()
    if result.get("id"):
        result["id"] = str(result["id"])
    transfer = result.get("transfer_numbers")
    if transfer and isinstance(transfer, str):
        try:
            result["transfer_numbers"] = json.loads(transfer)
        except Exception:
            pass
    return result


async def list_org_configs(org_id: str | None = None) -> list[dict]:
    if org_id:
        query = "SELECT * FROM org_configs WHERE org_id = $1 ORDER BY created_at DESC"
        async with db_service.pool.acquire() as conn:
            rows = await conn.fetch(query, org_id)
    else:
        query = "SELECT * FROM org_configs ORDER BY created_at DESC"
        async with db_service.pool.acquire() as conn:
            rows = await conn.fetch(query)
    return [serialize_org_config(dict(r)) for r in rows]


async def get_org_config_by_phone(phone_number: str) -> Optional[dict]:
    clean_number = phone_number.replace("+", "")
    query = "SELECT * FROM org_configs WHERE phone_number IN ($1, $2)"
    async with db_service.pool.acquire() as conn:
        row = await conn.fetchrow(query, phone_number, clean_number)
    return serialize_org_config(dict(row)) if row else None


async def upsert_org_config(
    org_id: str,
    phone_number: str,
    name: str,
    prompt: str,
    voice: str,
    model: str,
    kb_tags: list,
    transfer_numbers: dict,
    client_name: str,
    process_id: str | None,
    sip_trunk_id: str,
    dispatch_rule_id: str,
) -> str | None:
    clean_number = phone_number.replace("+", "")
    query = """
        INSERT INTO org_configs (
            org_id, phone_number, name, prompt, voice, model,
            kb_tags, transfer_numbers, client_name, process_id,
            sip_trunk_id, dispatch_rule_id
        ) VALUES (
            $1, $2, $3, $4, $5, $6,
            $7, $8, $9, $10,
            $11, $12
        )
        ON CONFLICT (phone_number) DO UPDATE SET
            org_id = EXCLUDED.org_id,
            name = EXCLUDED.name,
            prompt = EXCLUDED.prompt,
            voice = EXCLUDED.voice,
            model = EXCLUDED.model,
            kb_tags = EXCLUDED.kb_tags,
            transfer_numbers = EXCLUDED.transfer_numbers,
            client_name = EXCLUDED.client_name,
            process_id = EXCLUDED.process_id,
            sip_trunk_id = EXCLUDED.sip_trunk_id,
            dispatch_rule_id = EXCLUDED.dispatch_rule_id,
            is_active = true,
            updated_at = NOW()
        RETURNING id;
    """
    try:
        async with db_service.pool.acquire() as conn:
            org_config_id = await conn.fetchval(
                query,
                str(org_id),
                clean_number,
                name,
                prompt,
                voice,
                model,
                kb_tags,
                json.dumps(transfer_numbers),
                client_name,
                process_id,
                sip_trunk_id,
                dispatch_rule_id,
            )
        return str(org_config_id) if org_config_id else None
    except Exception as e:
        logger.error("Failed to save org_config: %s", e)
        return None


async def update_org_config(phone_number: str, payload: dict) -> Optional[dict]:
    clean_number = phone_number.replace("+", "")
    async with db_service.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM org_configs WHERE phone_number IN ($1, $2)",
            phone_number,
            clean_number,
        )
        if not row:
            return None

        update_fields: list[str] = []
        values: list[Any] = [row["id"]]
        idx = 2
        allowed_fields = [
            "name",
            "prompt",
            "voice",
            "model",
            "kb_tags",
            "transfer_numbers",
            "client_name",
            "process_id",
            "is_active",
        ]
        for field in allowed_fields:
            if field in payload:
                val = payload[field]
                if field == "transfer_numbers" and isinstance(val, dict):
                    val = json.dumps(val)
                update_fields.append(f"{field} = ${idx}")
                values.append(val)
                idx += 1

        if not update_fields:
            return {"message": "No valid fields to update"}

        update_fields.append("updated_at = NOW()")
        query = f"UPDATE org_configs SET {', '.join(update_fields)} WHERE id = $1 RETURNING *"
        updated_row = await conn.fetchrow(query, *values)
    return serialize_org_config(dict(updated_row)) if updated_row else None


async def deactivate_org_config(phone_number: str) -> bool:
    clean_number = phone_number.replace("+", "")
    query = """
        UPDATE org_configs SET is_active = false, updated_at = NOW()
        WHERE phone_number IN ($1, $2) RETURNING id
    """
    async with db_service.pool.acquire() as conn:
        row = await conn.fetchrow(query, phone_number, clean_number)
    return row is not None
