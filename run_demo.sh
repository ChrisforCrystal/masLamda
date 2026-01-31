#!/bin/bash
set -e

# Set up environment
export PYTHONPATH=$(pwd)
unset http_proxy https_proxy all_proxy

echo "🚀 [System] Starting Unified Sandbox Gateway..."
# Start Gateway in background
./venv/bin/uvicorn gateway.main:app > gateway.log 2>&1 &
GATEWAY_PID=$!

echo "⏳ [System] Waiting for Gateway to be ready..."
sleep 5

echo "---------------------------------------------------"
echo "🤖 [System] Starting AI Agent..."
echo "---------------------------------------------------"

# Run the Python Agent Demo
./venv/bin/python examples/agent_demo.py

echo "---------------------------------------------------"
echo "✅ [System] Demo Complete!"

# Cleanup
kill $GATEWAY_PID
