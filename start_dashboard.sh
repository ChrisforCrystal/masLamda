#!/bin/bash
set -e

# Cleanup
pkill -f flash-runner || true
pkill -f flash-controller || true
sleep 1

# Start Runner
echo "Starting Flash Runner..."
./flash-runner/target/debug/flash-runner > runner.log 2>&1 &
RUNNER_PID=$!

# Start Controller
echo "Starting Flash Controller..."
./flash-controller/flash-controller > controller.log 2>&1 &
CONTROLLER_PID=$!

echo "Services started!"
echo "Dashboard available at: http://localhost:8999/dashboard"
echo "Press Ctrl+C to stop..."

# Keep running
wait $RUNNER_PID $CONTROLLER_PID
