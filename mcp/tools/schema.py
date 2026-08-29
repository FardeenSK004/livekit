"""Schema and query inspection MCP tools."""

import json
from typing import List
from db import get_db_connection


async def list_tables() -> List[str]:
    """List all user tables in the database."""
    conn = await get_db_connection()
    try:
        rows = await conn.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"
        )
        return [r["table_name"] for r in rows]
    finally:
        await conn.close()


async def describe_table(table_name: str) -> str:
    """Describe columns and datatypes of a table."""
    conn = await get_db_connection()
    try:
        rows = await conn.fetch(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = $1
            ORDER BY ordinal_position
            """,
            table_name,
        )
        if not rows:
            return f"Table '{table_name}' not found."
        cols = [dict(r) for r in rows]
        return json.dumps(cols, indent=2)
    finally:
        await conn.close()


async def execute_query(query: str) -> str:
    """Execute arbitrary SQL query."""
    conn = await get_db_connection()
    try:
        if query.strip().upper().startswith("SELECT"):
            rows = await conn.fetch(query)
            return json.dumps([dict(r) for r in rows], indent=2, default=str)
        else:
            status = await conn.execute(query)
            return f"Query executed: {status}"
    except Exception as e:
        return f"Error executing query: {e}"
    finally:
        await conn.close()


async def get_db_status() -> str:
    """Get database server status and connection test."""
    conn = await get_db_connection()
    try:
        row = await conn.fetchrow("SELECT version(), current_database(), current_user")
        return json.dumps(dict(row), indent=2)
    finally:
        await conn.close()
