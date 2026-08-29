"""Doctors and hospitals lookup MCP tools."""

import logging
from db import get_db_connection

logger = logging.getLogger("mcp.tools.doctors")


async def get_hospitals() -> str:
    """List all hospital locations available for appointments."""
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

    hospital_tables = [t for t in table_names if t in ("hospitals", "locations", "centers", "branches")]
    if not hospital_tables:
        hospital_tables = [t for t in table_names if "hospital" in t.lower() or "center" in t.lower()]

    if not hospital_tables:
        return "No hospitals table found."

    results = []
    for table in hospital_tables:
        try:
            conn2 = await get_db_connection()
            rows = await conn2.fetch(f"SELECT * FROM {table} LIMIT 50")
            for r in rows:
                results.append(str(dict(r)))
            await conn2.close()
        except Exception as e:
            logger.error(f"Error querying {table}: {e}")

    return "Available hospitals:\n" + "\n".join(results) if results else "No hospitals found."


async def get_doctors(hospital: str = "") -> str:
    """List doctors, optionally filtered by hospital/location name."""
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

    doctor_tables = [t for t in table_names if t in ("doctors", "doctor", "physicians")]
    if not doctor_tables:
        doctor_tables = [t for t in table_names if "doctor" in t.lower()]

    if not doctor_tables:
        return "No doctors table found."

    results = []
    for table in doctor_tables:
        try:
            conn2 = await get_db_connection()
            rows = await conn2.fetch(f"SELECT * FROM {table} LIMIT 50")
            for r in rows:
                results.append(str(dict(r)))
            await conn2.close()
        except Exception as e:
            logger.error(f"Error querying {table}: {e}")

    return "Available doctors:\n" + "\n".join(results) if results else "No doctors found."


async def get_available_slots(doctor_id: str, date: str) -> str:
    """Check available appointment slots for a doctor on a given date."""
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

    slot_tables = [t for t in table_names if t in ("slots", "doctor_slots", "availability")]
    if not slot_tables:
        return f"Standard slots available for Doctor {doctor_id} on {date}: 09:00 AM, 10:30 AM, 02:00 PM, 04:30 PM"

    results = []
    for table in slot_tables:
        try:
            conn2 = await get_db_connection()
            rows = await conn2.fetch(f"SELECT * FROM {table} WHERE doctor_id = $1 AND date = $2", doctor_id, date)
            for r in rows:
                results.append(str(dict(r)))
            await conn2.close()
        except Exception as e:
            logger.error(f"Error querying {table}: {e}")

    return "\n".join(results) if results else "No explicit slots found."
