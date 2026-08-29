#!/bin/bash

# Function to handle cleanup on exit
cleanup() {
    echo ""
    echo "Stopping services..."
    kill $MCP_PID $AGENT_PID $UI_PID 2>/dev/null
    exit
}

# Trap SIGINT (Ctrl+C) and SIGTERM
trap cleanup SIGINT SIGTERM

echo "Starting MCP Database Server..."
uv run python mcp/server.py &
MCP_PID=$!

echo "Starting LiveKit Voice Agent (dev mode)..."
uv run python -m core.agent dev &
AGENT_PID=$!

echo "Starting FastAPI Application..."
uv run python app.py &
UI_PID=$!

LOCAL_IP=$(hostname -I | awk '{print $1}')
if [ -z "$LOCAL_IP" ]; then
    LOCAL_IP="localhost"
fi

echo ""
echo "----------------------------------------------------------------"
echo " Everything is running!"
echo " Webhook URL:  http://$LOCAL_IP:8081/api/v1/webhooks/telephony"
echo " Dashboard:    http://$LOCAL_IP:8081/dashboard"
echo " Test Console: http://$LOCAL_IP:8081/console"
echo " Healthcheck:  http://$LOCAL_IP:8081/health"
echo " MCP Server:   MCP protocol on stdio"
echo "----------------------------------------------------------------"
echo "Press Ctrl+C to stop all services."

# Wait for background processes to finish
wait $MCP_PID $AGENT_PID $UI_PID
