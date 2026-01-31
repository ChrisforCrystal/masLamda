#!/bin/bash

# Kill Gateway
pkill -f "uvicorn gateway.main:app" || true

# Delete Sandbox Pods
kubectl delete pod -l app=sandbox --force --grace-period=0 2>/dev/null || true

echo "🧹 Cleanup complete (Processes killed, Pods deleted)."
