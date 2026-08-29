#!/bin/bash
set -e

case "$1" in
  agent)
    echo "Starting LiveKit Voice Agent..."
    exec uv run python -m core.agent start
    ;;
  ui)
    echo "Starting FastAPI Application..."
    exec uv run python app.py
    ;;
  dispatcher)
    echo "Starting Dispatcher Routine..."
    exec uv run python -m core.dispatcher
    ;;
  mcp)
    echo "Starting MCP Database Server..."
    exec uv run python mcp/server.py
    ;;
  *)
    echo "Usage: $0 {agent|ui|dispatcher|mcp}"
    echo "Defaulting to agent..."
    exec uv run python -m core.agent start
    ;;
esac
