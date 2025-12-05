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

sleep 5

# Create an infinite loop WAT module
echo '(module (func (export "_start") (loop (br 0))))' > infinite.wat

# Run Infinite Loop
echo "Running Infinite Loop Module (Should fail)..."
RESPONSE=$(curl -s -X POST http://localhost:8999/run --data-binary @infinite.wat)
echo "Response: $RESPONSE"

# Check for error
if echo "$RESPONSE" | grep -q "fuel"; then
    echo "SUCCESS: Infinite loop terminated by fuel limit."
else
    echo "FAILURE: Infinite loop NOT terminated as expected."
    exit 1
fi

# Cleanup
kill $RUNNER_PID
kill $CONTROLLER_PID
