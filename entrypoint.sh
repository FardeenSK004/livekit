#!/bin/bash
set -e

case "$1" in
  agent)
    echo "Starting LiveKit Agent..."
    exec uv run python -m mantra.agent start
    ;;
  ui)
    echo "Starting UI Server (FastAPI)..."
    exec uv run python -m mantra.ui_server
    ;;
  mcp)
    echo "Starting MCP Database Server..."
    exec uv run python mcp/server.py
    ;;
  backfill)
    echo "Running KB embedding backfill..."
    shift
    exec uv run python tools/backfill_embeddings.py "$@"
    ;;
  *)
    echo "Usage: $0 {agent|ui|mcp|backfill [--kb-id X] [--batch-size N] [--limit N] [--dry-run]}"
    echo "Defaulting to agent..."
    exec uv run python -m mantra.agent start
    ;;
esac
