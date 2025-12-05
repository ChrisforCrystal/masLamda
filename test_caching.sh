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

# Create a simple WAT module
echo '(module (func (export "_start")))' > test.wat

# First Run (Cold Start)
echo "First Run (Should be Cache Miss)..."
curl -X POST http://localhost:8999/run --data-binary @test.wat
echo ""

# Second Run (Warm Start)
echo "Second Run (Should be Cache Hit)..."
curl -X POST http://localhost:8999/run --data-binary @test.wat
echo ""

# Check logs for Cache Hit/Miss
echo "Checking Runner Logs..."
grep "Cache" runner.log

# Cleanup
kill $RUNNER_PID
kill $CONTROLLER_PID
