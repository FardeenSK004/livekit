"""Call logs and history querying MCP tools."""

import json
import logging
from db import get_db_connection

logger = logging.getLogger("mcp.tools.call_logs")


async def call_logs(log_data: dict) -> str:
    """Upsert a call log entry into the call_logs table based on call_id."""
    conn = await get_db_connection()
    if not conn:
        return "Error: Could not connect to database"

    call_id = log_data.get("call_id", "")
    if not call_id:
        await conn.close()
        return "Error: call_id is required in log_data"

    try:
        call_log_val = log_data.get("call_log")
        if isinstance(call_log_val, (dict, list)):
            call_log_val = json.dumps(call_log_val)

        status_val = log_data.get("status", "")
        recording_url_val = log_data.get("recording_url", "")

        row = await conn.fetchrow(
            """
            INSERT INTO call_logs (call_id, call_log, status, recording_url)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (call_id) DO UPDATE 
            SET call_log = EXCLUDED.call_log,
                status = EXCLUDED.status,
                recording_url = EXCLUDED.recording_url
            RETURNING id
            """,
            call_id,
            call_log_val,
            status_val,
            recording_url_val,
        )
        return f"Successfully processed call log with ID: {row['id']}" if row else f"Processed call_id: {call_id}"
    except Exception as e:
        return f"Error processing call log: {e}"
    finally:
        await conn.close()


async def get_call_history(identifier: str, limit: int = 5) -> str:
    """Look up past call logs for a patient/phone number."""
    conn = await get_db_connection()
    if not conn:
        return "Error: Could not connect to database"

    try:
        clean = identifier.strip().lstrip("+").replace(" ", "")
        rows = await conn.fetch(
            """
            SELECT call_id, status, recording_url, caller_number, called_number, created_at, call_log
            FROM call_logs
            WHERE caller_number LIKE $1 OR called_number LIKE $1 OR call_id LIKE $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            f"%{clean}%",
            limit,
        )
        return "\n".join([str(dict(r)) for r in rows]) if rows else f"No call history found for '{identifier}'."
    except Exception as e:
        return f"Error fetching call history: {e}"
    finally:
        await conn.close()
