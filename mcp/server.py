"""
MCP (Model Context Protocol) Database Server for Mantra Voice Agent.
Modular server exposing database inspection, patients, appointments, and call log tools.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP
from tools.schema import list_tables, describe_table, execute_query, get_db_status
from tools.patients import get_patient_info
from tools.doctors import get_hospitals, get_doctors, get_available_slots
from tools.appointments import create_appointment, update_appointment, get_appointments
from tools.call_logs import call_logs, get_call_history

mcp = FastMCP("MantraDB")

# Register all modular tools
mcp.tool()(list_tables)
mcp.tool()(describe_table)
mcp.tool()(execute_query)
mcp.tool()(get_db_status)
mcp.tool()(get_patient_info)
mcp.tool()(get_hospitals)
mcp.tool()(get_doctors)
mcp.tool()(get_available_slots)
mcp.tool()(create_appointment)
mcp.tool()(update_appointment)
mcp.tool()(get_appointments)
mcp.tool()(call_logs)
mcp.tool()(get_call_history)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
