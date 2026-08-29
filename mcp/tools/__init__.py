"""MCP Tools collection."""

from .schema import list_tables, describe_table, execute_query, get_db_status
from .patients import get_patient_info
from .doctors import get_hospitals, get_doctors, get_available_slots
from .appointments import create_appointment, update_appointment, get_appointments
from .call_logs import call_logs, get_call_history

__all__ = [
    "list_tables",
    "describe_table",
    "execute_query",
    "get_db_status",
    "get_patient_info",
    "get_hospitals",
    "get_doctors",
    "get_available_slots",
    "create_appointment",
    "update_appointment",
    "get_appointments",
    "call_logs",
    "get_call_history",
]
