"""PostgreSQL database service."""

from __future__ import annotations

from typing import Any, Optional

import asyncpg

from app.config import settings


class DatabaseService:
    def __init__(self):
        self._pool: asyncpg.Pool | None = None

    async def start(self):
        self._pool = await asyncpg.create_pool(
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            database=settings.POSTGRES_DB,
            host=settings.POSTGRES_HOST,
            port=int(settings.POSTGRES_PORT),
            min_size=2,
            max_size=10,
        )

    async def stop(self):
        if self._pool:
            await self._pool.close()
            self._pool = None

    @property
    def pool(self) -> asyncpg.Pool:
        if not self._pool:
            raise RuntimeError("DB not initialized. Call start() first.")
        return self._pool

    async def acquire(self):
        """Acquire a connection from the pool (context manager)."""
        return self.pool.acquire()

    async def save_call_log(
        self, call_id: str, call_log: str, status: str, recording_url: str
    ):
        query = """
        INSERT INTO call_logs (call_id, call_log, status, recording_url)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (call_id) DO UPDATE
        SET call_log = EXCLUDED.call_log,
            status = EXCLUDED.status,
            recording_url = EXCLUDED.recording_url;
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, call_id, call_log, status, recording_url)

    async def get_call_logs(self, limit: int = 50, offset: int = 0) -> list[dict]:
        query = """
        SELECT call_id, status, recording_url, created_at
        FROM call_logs
        ORDER BY created_at DESC
        LIMIT $1 OFFSET $2
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, limit, offset)
            return [dict(r) for r in rows]

    async def get_today_metrics(self) -> dict[str, Any]:
        query = """
        SELECT
            COUNT(*) as total,
            COALESCE(AVG(CASE WHEN status = 'completed' THEN 1.0 ELSE 0.0 END), 0) as answer_rate
        FROM call_logs
        WHERE created_at >= CURRENT_DATE
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query)
            return {
                "total": row["total"] if row else 0,
                "answer_rate": float(row["answer_rate"]) if row else 0.0,
            }

    async def get_org_config_by_phone(self, phone_number: str) -> Optional[dict]:
        query = """
        SELECT *
        FROM org_configs
        WHERE phone_number = $1 AND is_active = true
        LIMIT 1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, phone_number)
            return dict(row) if row else None

    async def get_org_config_sip_trunk(self, phone_number: str, clean_number: str) -> Optional[str]:
        query = """
        SELECT sip_trunk_id FROM org_configs WHERE phone_number IN ($1, $2)
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, phone_number, clean_number)
            if row and row["sip_trunk_id"]:
                return row["sip_trunk_id"]
        return None

    async def get_dashboard_metrics(self) -> dict[str, Any]:
        query = """
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
                        WHERE call_log::json ->> 'call_duration_seconds' ~ '^\\d+$'
                    )
                )::int AS avg_duration_seconds
            FROM call_logs
            WHERE created_at >= CURRENT_DATE
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query)
        if not row:
            return {
                "total_calls": 0,
                "completed_calls": 0,
                "busy_calls": 0,
                "no_answer_calls": 0,
                "error_calls": 0,
                "incomplete_calls": 0,
                "avg_duration_seconds": 0,
            }
        return dict(row)

    async def get_dashboard_calls(self, limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
        query = """
            SELECT call_id, status, recording_url, created_at,
                   call_log::json AS call_log
            FROM call_logs
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
        """
        count_query = "SELECT COUNT(*)::int AS total FROM call_logs"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, limit, offset)
            count_row = await conn.fetchrow(count_query)
        total = count_row["total"] if count_row else 0
        calls = []
        for row in rows:
            cl = row["call_log"] if isinstance(row["call_log"], dict) else {}
            calls.append(
                {
                    "call_id": row["call_id"],
                    "status": row["status"],
                    "recording_url": row["recording_url"] or "",
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "client_name": cl.get("client_name") or cl.get("client_id") or "",
                    "client_phone": cl.get("client_phone") or "",
                    "duration": cl.get("call_duration_seconds"),
                    "summary": cl.get("ai_summary") or "",
                    "purpose": (cl.get("prompt") or "")[:120],
                }
            )
        return calls, total

    async def list_kb_ids(self) -> list[str]:
        query = "SELECT DISTINCT kb_id FROM kb_pages ORDER BY kb_id"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
        return [r["kb_id"] for r in rows]


db_service = DatabaseService()
