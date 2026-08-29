"""Patient search and management MCP tools."""

import logging
from db import get_db_connection

logger = logging.getLogger("mcp.tools.patients")


async def get_patient_info(identifier: str) -> str:
    """Look up patient info by phone number or ID."""
    conn = await get_db_connection()
    if not conn:
        return "Error: Could not connect to database"

    try:
        tables = await conn.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        table_names = [r["table_name"] for r in tables]
    finally:
        await conn.close()

    search_term = identifier.strip().lstrip("+").replace(" ", "")
    patient_tables = [t for t in table_names if t in ("patients", "leads", "patient", "lead")]
    if not patient_tables:
        patient_tables = [t for t in table_names if "patient" in t.lower() or "lead" in t.lower()]
    if not patient_tables:
        return "No patients or leads table found in the database."

    results = []
    for table in patient_tables:
        try:
            conn2 = await get_db_connection()
            cols = await conn2.fetch(
                "SELECT column_name FROM information_schema.columns WHERE table_name = $1",
                table,
            )
            col_names = [c["column_name"] for c in cols]
            select_cols = [c for c in col_names if c in ("id", "name", "full_name", "phone", "email")] or ["*"]
            select_expr = ", ".join(select_cols)

            phone_cols = [c for c in col_names if "phone" in c or "mobile" in c]
            row = None
            for pcol in phone_cols:
                row = await conn2.fetchrow(
                    f"SELECT {select_expr} FROM {table} WHERE {pcol} LIKE $1 LIMIT 1",
                    f"%{search_term}",
                )
                if row:
                    break

            if row:
                parts = [f"[{table}]"]
                for col in row.keys():
                    parts.append(f"{col}: {row[col]}")
                results.append(" | ".join(parts))

            await conn2.close()
        except Exception as e:
            logger.error(f"Error searching {table}: {e}")

    if results:
        return "Found patient(s):\n" + "\n".join(results)
    return f"No patient found matching '{identifier}'."
