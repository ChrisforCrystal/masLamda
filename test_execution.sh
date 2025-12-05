#!/bin/bash
set -e

# Cleanup existing processes
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

sleep 5

# Create a simple WAT module (wasm text format)
# This module just exports a _start function that does nothing.
echo '(module (func (export "_start")))' > test.wat

# Send request
echo "Sending request..."
curl -X POST http://localhost:8999/run --data-binary @test.wat

# Cleanup
kill $RUNNER_PID
kill $CONTROLLER_PID
