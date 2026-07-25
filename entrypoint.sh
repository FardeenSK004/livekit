#!/bin/bash
set -e

case "$1" in
  agent)
    echo "Starting LiveKit Agent..."
    exec uv run python -m app.agent.entrypoint start
    ;;
  ui)
    echo "Starting UI Server (FastAPI)..."
    exec uv run python -m app.main
    ;;
  dispatcher)
    echo "Starting Call Dispatcher..."
    exec uv run python -m app.routines
    ;;
  mcp)
    echo "Starting MCP Database Server..."
    exec uv run python mcp/server.py
    ;;
  *)
    echo "Usage: $0 {agent|ui|dispatcher|mcp}"
    echo "Defaulting to agent..."
    exec uv run python -m app.agent.entrypoint start
    ;;
esac
