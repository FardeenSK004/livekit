"""Appointment booking, updating, and querying MCP tools."""

import logging
from db import get_db_connection

logger = logging.getLogger("mcp.tools.appointments")


async def create_appointment(
    patient_id: str,
    doctor_id: str,
    slot_time: str,
    hospital: str = "",
    notes: str = "",
    patient_name: str = "",
    patient_phone: str = "",
) -> str:
    """Book a new appointment."""
    conn = await get_db_connection()
    if not conn:
        return "Error: Could not connect to database"

    try:
        row = await conn.fetchrow(
            """
            INSERT INTO appointments (patient_id, doctor_id, appointment_date, hospital, notes, status, created_at)
            VALUES ($1, $2, $3, $4, $5, 'Scheduled', NOW())
            RETURNING id
            """,
            patient_id, doctor_id, slot_time, hospital, notes,
        )
        return f"Appointment created successfully with ID: {row['id']}"
    except Exception as e:
        logger.error(f"Error creating appointment: {e}")
        return f"Error booking appointment: {e}"
    finally:
        await conn.close()


async def update_appointment(appointment_id: str, updates: dict) -> str:
    """Update fields on an existing appointment."""
    conn = await get_db_connection()
    if not conn:
        return "Error: Could not connect to database"

    try:
        set_clauses = []
        values = [appointment_id]
        for idx, (k, v) in enumerate(updates.items(), start=2):
            set_clauses.append(f"{k} = ${idx}")
            values.append(v)

        if not set_clauses:
            return "No update fields provided."

        query = f"UPDATE appointments SET {', '.join(set_clauses)} WHERE id = $1 RETURNING id"
        row = await conn.fetchrow(query, *values)
        if row:
            return f"Appointment {appointment_id} updated successfully."
        return f"Appointment {appointment_id} not found."
    except Exception as e:
        return f"Error updating appointment: {e}"
    finally:
        await conn.close()


async def get_appointments(patient_id: str = "", doctor_id: str = "", date: str = "", status: str = "") -> str:
    """List appointments by patient, doctor, date, or status."""
    conn = await get_db_connection()
    if not conn:
        return "Error: Could not connect to database"

    try:
        conditions = []
        params = []
        if patient_id:
            conditions.append(f"patient_id = ${len(params)+1}")
            params.append(patient_id)
        if doctor_id:
            conditions.append(f"doctor_id = ${len(params)+1}")
            params.append(doctor_id)
        if status:
            conditions.append(f"status = ${len(params)+1}")
            params.append(status)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = await conn.fetch(f"SELECT * FROM appointments {where} ORDER BY created_at DESC LIMIT 50", *params)
        return "\n".join([str(dict(r)) for r in rows]) if rows else "No appointments found."
    except Exception as e:
        return f"Error fetching appointments: {e}"
    finally:
        await conn.close()
