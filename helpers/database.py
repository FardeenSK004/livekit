"""Database operations and PostgreSQL logging helpers."""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional, Union, Dict, Any
import asyncpg

logger = logging.getLogger("mantra.helpers.database")


async def get_db_connection() -> Optional[asyncpg.Connection]:
    """Get an asynchronous PostgreSQL database connection."""
    db_user = os.getenv("POSTGRES_USER")
    db_password = os.getenv("POSTGRES_PASSWORD")
    db_name = os.getenv("POSTGRES_DB")
    db_host = os.getenv("POSTGRES_HOST")
    db_port = os.getenv("POSTGRES_PORT")

    if not all([db_user, db_password, db_name, db_host, db_port]):
        return None

    try:
        conn = await asyncpg.connect(
            user=db_user,
            password=db_password,
            database=db_name,
            host=db_host,
            port=db_port,
            timeout=5.0,
        )
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        return None


async def save_call_log_to_db(
    call_id_or_dict: Union[str, Dict[str, Any]],
    call_log: Optional[Union[str, Dict[str, Any]]] = None,
    status: Optional[str] = None,
    recording_url: Optional[str] = None,
    caller_number: str = "",
    called_number: str = "",
    trunk_id: str = "",
):
    """Save call details to PostgreSQL call_logs table with attempt history array."""
    if isinstance(call_id_or_dict, dict):
        d = call_id_or_dict
        call_id = str(d.get("call_id", ""))
        call_log = d.get("call_log", "")
        status = d.get("status", "")
        recording_url = d.get("recording_url", "")
        caller_number = d.get("caller_number", "")
        called_number = d.get("called_number", "")
        trunk_id = d.get("trunk_id", "")
    else:
        call_id = str(call_id_or_dict)
        status = status or ""
        recording_url = recording_url or ""

    conn = await get_db_connection()
    if not conn:
        return

    try:
        log_data = {}
        try:
            log_data = json.loads(call_log) if isinstance(call_log, str) else (call_log or {})
        except Exception:
            pass

        attempted_at = (
            log_data.get("called_on")
            or log_data.get("requested_at")
            or datetime.now(tz=timezone.utc).isoformat()
        )
        ai_call_id = log_data.get("ai_call_id") or (log_data.get("data", {}) if isinstance(log_data, dict) else {}).get("ai_call_id") or ""
        duration = log_data.get("call_duration") or log_data.get("call_duration_seconds") or 0

        # Fetch existing attempts
        existing_row = await conn.fetchrow(
            "SELECT caller_number, called_number, attempts FROM call_logs WHERE call_id = $1;",
            str(call_id),
        )

        existing_attempts = []
        db_caller = ""
        db_called = ""
        if existing_row:
            db_caller = existing_row["caller_number"] or ""
            db_called = existing_row["called_number"] or ""
            raw_att = existing_row["attempts"]
            if isinstance(raw_att, str):
                try:
                    existing_attempts = json.loads(raw_att)
                except Exception:
                    existing_attempts = []
            elif isinstance(raw_att, list):
                existing_attempts = list(raw_att)

        final_caller = caller_number or db_caller or ""
        final_called = called_number or db_called or ""

        # Avoid duplicate attempt recording
        current_attempt = {
            "attempted_at": attempted_at,
            "status": status,
            "recording_url": recording_url,
            "duration": duration,
            "ai_call_id": ai_call_id,
        }

        is_duplicate = False
        for att in existing_attempts:
            if att.get("attempted_at") == attempted_at and att.get("status") == status:
                is_duplicate = True
                break

        if not is_duplicate:
            existing_attempts.append(current_attempt)

        attempts_json = json.dumps(existing_attempts)
        call_log_json = json.dumps(log_data) if isinstance(log_data, dict) else str(call_log or "{}")

        await conn.execute(
            """
            INSERT INTO call_logs (
                call_id, caller_number, called_number, trunk_id,
                call_log, status, recording_url, attempts, created_at
            )
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8::jsonb, NOW())
            ON CONFLICT (call_id) DO UPDATE SET
                caller_number = COALESCE(NULLIF(EXCLUDED.caller_number, ''), call_logs.caller_number),
                called_number = COALESCE(NULLIF(EXCLUDED.called_number, ''), call_logs.called_number),
                trunk_id = COALESCE(NULLIF(EXCLUDED.trunk_id, ''), call_logs.trunk_id),
                call_log = EXCLUDED.call_log,
                status = EXCLUDED.status,
                recording_url = COALESCE(NULLIF(EXCLUDED.recording_url, ''), call_logs.recording_url),
                attempts = EXCLUDED.attempts;
            """,
            str(call_id),
            final_caller,
            final_called,
            trunk_id or "",
            call_log_json,
            status,
            recording_url,
            attempts_json,
        )
    except Exception as e:
        logger.error(f"Error saving call log to DB for call_id {call_id}: {e}")
    finally:
        await conn.close()


async def save_call_event(
    call_id: str,
    event_type: str,
    event_source: str = "ui_server",
    event_payload: Optional[dict] = None,
    payload: Optional[dict] = None,
    event_status: str = "success",
    event_error: str = "",
    event_log: str = "",
    ai_call_id: str = "",
):
    """Save a single call-lifecycle event to the call_events audit table."""
    conn = await get_db_connection()
    if not conn:
        return

    ep = event_payload if event_payload is not None else (payload or {})
    extracted_ai_call_id = (
        ai_call_id
        or (ep.get("ai_call_id") if isinstance(ep, dict) else "")
        or (ep.get("job_id") if isinstance(ep, dict) else "")
        or (ep.get("data", {}).get("ai_call_id") if isinstance(ep, dict) and isinstance(ep.get("data"), dict) else "")
        or ""
    )

    try:
        await conn.execute(
            """
            INSERT INTO call_events (call_id, event_type, event_source, event_payload, event_log, event_status, event_error, ai_call_id, created_at)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, NOW())
            ON CONFLICT (call_id, event_type) DO UPDATE
            SET event_payload = EXCLUDED.event_payload,
                event_log     = EXCLUDED.event_log,
                event_status  = EXCLUDED.event_status,
                event_error   = EXCLUDED.event_error,
                ai_call_id    = EXCLUDED.ai_call_id;
            """,
            str(call_id),
            event_type,
            event_source,
            json.dumps(ep, default=str),
            event_log,
            event_status,
            event_error,
            extracted_ai_call_id,
        )
    except Exception as e:
        logger.error(f"Error saving call event for call_id {call_id}: {e}")
    finally:
        await conn.close()
