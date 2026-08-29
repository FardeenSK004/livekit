"""Dashboard and metrics controller."""

import os
import json
import time
import asyncio
import logging
from typing import Optional
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
from dependencies.database import get_db_connection

logger = logging.getLogger("controllers.dashboard")


class DashboardController:
    """Controller for dashboard metrics, real-time SSE stream, and call logs."""

    @staticmethod
    async def get_metrics():
        try:
            conn = await get_db_connection()
            try:
                row = await conn.fetchrow("""
                    SELECT
                        COUNT(*)::int AS total_calls,
                        COUNT(*) FILTER (WHERE status = 'Completed')::int AS completed_calls,
                        COUNT(*) FILTER (WHERE status = 'Busy')::int AS busy_calls,
                        COUNT(*) FILTER (WHERE status = 'No Answer')::int AS no_answer_calls,
                        COUNT(*) FILTER (WHERE status = 'Error')::int AS error_calls,
                        COUNT(*) FILTER (WHERE status = 'Incomplete')::int AS incomplete_calls,
                        ROUND(
                            AVG(
                                CAST(NULLIF(call_log::json ->> 'call_duration_seconds', '') AS integer)
                            ) FILTER (
                                WHERE call_log::json ->> 'call_duration_seconds' ~ '^[0-9]+$'
                            )
                        )::int AS avg_duration_seconds
                    FROM call_logs
                    WHERE created_at >= CURRENT_DATE
                """)
            finally:
                await conn.close()

            metrics = dict(row) if row else {
                "total_calls": 0, "completed_calls": 0, "busy_calls": 0,
                "no_answer_calls": 0, "error_calls": 0, "incomplete_calls": 0,
                "avg_duration_seconds": 0,
            }
            answer_rate = (
                round(metrics["completed_calls"] / metrics["total_calls"] * 100, 1)
                if metrics.get("total_calls", 0) > 0 else 0
            )
            return {**metrics, "answer_rate": answer_rate}
        except Exception as e:
            logger.error(f"Dashboard metrics error: {e}")
            return {"error": str(e)}

    @staticmethod
    async def get_calls(limit: int = 20, offset: int = 0, search: str = None, status: str = None):
        try:
            conn = await get_db_connection()
            try:
                conditions = []
                params = []
                param_idx = 1

                if search and search.strip():
                    conditions.append(f"(CAST(call_id AS TEXT) ILIKE ${param_idx} OR caller_number ILIKE ${param_idx} OR called_number ILIKE ${param_idx} OR call_log::text ILIKE ${param_idx})")
                    params.append(f"%{search.strip()}%")
                    param_idx += 1

                if status and status.strip() and status.lower() != "all":
                    st_clean = status.strip().replace(" ", "").replace("_", "").lower()
                    conditions.append(f"REPLACE(REPLACE(LOWER(status), '_', ''), ' ', '') LIKE ${param_idx}")
                    params.append(f"%{st_clean}%")
                    param_idx += 1

                where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

                query = f"""
                    SELECT call_id, status, recording_url, created_at, caller_number, called_number, trunk_id,
                           call_log::json AS call_log,
                           COALESCE(attempts, '[]'::jsonb) AS attempts
                    FROM call_logs
                    {where_clause}
                    ORDER BY created_at DESC
                    LIMIT ${param_idx} OFFSET ${param_idx + 1}
                """
                params_with_limit = params + [limit, offset]
                rows = await conn.fetch(query, *params_with_limit)

                count_query = f"SELECT COUNT(*)::int AS total FROM call_logs {where_clause}"
                count_row = await conn.fetchrow(count_query, *params)
                total = count_row["total"] if count_row else 0
            finally:
                await conn.close()

            calls = []
            for row in rows:
                cl_raw = row["call_log"]
                cl = json.loads(cl_raw) if isinstance(cl_raw, str) else (cl_raw if isinstance(cl_raw, dict) else {})
                attempts_raw = row.get("attempts")
                attempts_list = json.loads(attempts_raw) if isinstance(attempts_raw, str) else (attempts_raw if isinstance(attempts_raw, list) else [])

                calls.append({
                    "call_id": row["call_id"],
                    "status": row["status"],
                    "recording_url": row["recording_url"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "caller_number": row["caller_number"],
                    "called_number": row["called_number"],
                    "trunk_id": row["trunk_id"],
                    "duration_seconds": cl.get("call_duration_seconds") or cl.get("call_duration", 0),
                    "summary": cl.get("ai_summary") or cl.get("summary", ""),
                    "sentiment_score": cl.get("sentiment_score"),
                    "attempts": attempts_list,
                })

            return {"total": total, "limit": limit, "offset": offset, "calls": calls}
        except Exception as e:
            logger.error(f"Dashboard calls error: {e}")
            return {"error": str(e)}

    @staticmethod
    async def get_active_calls(request: Request):
        lk_client = getattr(request.app.state, "lk_client", None)
        if not lk_client:
            return {"active_rooms": [], "count": 0}
        try:
            resp = await lk_client.room.list_rooms(api.ListRoomsRequest())
            rooms = [r.name for r in resp.rooms if (r.name or "").startswith("call_")]
            return {"active_rooms": rooms, "count": len(rooms)}
        except Exception as e:
            return {"error": str(e)}


dashboard_controller = DashboardController()
