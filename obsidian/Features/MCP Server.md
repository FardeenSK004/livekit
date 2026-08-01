# MCP Server

**File:** `mcp/server.py` (1,073 lines)

## Overview

Model Context Protocol server exposing PostgreSQL as AI-accessible tools. Built with `mcp[cli]`. Provides database introspection, patient/doctor/hospital lookup, appointment booking, call history, and call log upsert capabilities.

## Tools

### Database Introspection

| Tool | Description |
|------|-------------|
| `list_tables()` | List all tables in public schema |
| `describe_table(table_name)` | Column names, data types, nullability |
| `execute_query(query)` | Read-only SELECT/WITH (rejects modifications) |
| `get_db_status()` | Connection status, table count, row counts |

### Patient & Healthcare

| Tool | Description |
|------|-------------|
| `get_patient_info(identifier)` | Look up patient by phone number, patient ID, or lead ID across patients/leads tables |
| `get_hospitals()` | List hospital locations/centers/branches |
| `get_doctors(hospital)` | List doctors, optionally filtered by hospital name |
| `get_available_slots(doctor_id, date)` | Check appointment slots for a doctor on a given date |

### Appointments

| Tool | Description |
|------|-------------|
| `create_appointment(patient_id, doctor_id, slot_time, hospital, notes, patient_name, patient_phone)` | Book a new appointment with dynamic column mapping |
| `update_appointment(appointment_id, updates)` | Update an existing appointment (reschedule, cancel, change doctor) |
| `get_appointments(patient_id?, doctor_id?, date?, status?)` | Query appointments with optional filters |

### Call Data

| Tool | Description |
|------|-------------|
| `call_logs(log_data)` | Upsert call log by `call_id` — creates or updates call log entry |
| `get_call_history(identifier, limit=5)` | Retrieve call history for a patient by ID or phone number |

## Usage

```bash
uv run python mcp/server.py
```

## Security

- Only SELECT/WITH queries allowed via `execute_query`
- All tools use dynamic column mapping — adapt to the actual schema found in the database (table names and column names are auto-discovered)
- Connection params from environment (`POSTGRES_*`)
