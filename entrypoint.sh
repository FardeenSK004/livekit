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
  worker-processing)
    echo "Starting Webhook Processing Worker..."
    exec uv run celery -A mantra.webhook_tasks.celery_app worker -Q webhook_processing -c 2 --loglevel=info
    ;;
  worker-delivery)
    echo "Starting Webhook Delivery Worker..."
    exec uv run celery -A mantra.webhook_tasks.celery_app worker -Q webhook_delivery -c 2 --loglevel=info
    ;;
  *)
    echo "Usage: $0 {agent|ui|worker-processing|worker-delivery}"
    echo "Defaulting to agent..."
    exec uv run python -m mantra.agent start
    ;;
esac
