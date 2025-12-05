#!/bin/bash
set -e

# 1. Kill existing processes
echo "Killing existing processes..."
pkill -f flash-controller || true
pkill -f flash-runner || true
sleep 2

# 2. Start Runner
echo "Starting Flash Runner..."
cd flash-runner
cargo run > ../runner.log 2>&1 &
RUNNER_PID=$!
cd ..
sleep 10 # Wait for Runner to start

# 3. Start Controller
echo "Starting Flash Controller..."
cd flash-controller
go run main.go > ../controller.log 2>&1 &
CONTROLLER_PID=$!
cd ..
sleep 5 # Wait for Controller to start

# 4. Deploy Infinite Service
echo "Deploying infinite.wat..."
RESPONSE=$(curl -s -X POST http://localhost:8999/deploy -F "file=@infinite.wat")
echo "Deploy Response: $RESPONSE"

SERVICE_ID=$(echo $RESPONSE | jq -r '.service_id')
if [ "$SERVICE_ID" == "null" ] || [ -z "$SERVICE_ID" ]; then
    echo "Failed to deploy service"
    exit 1
fi
echo "Service ID: $SERVICE_ID"

# 5. List Services (Should be Running)
echo "Listing services..."
curl -s http://localhost:8999/services | jq .

# 6. Wait a bit to prove it's running
echo "Waiting 5 seconds..."
sleep 5

# 7. Stop Service
echo "Stopping service $SERVICE_ID..."
curl -s -X POST http://localhost:8999/services/$SERVICE_ID/stop | jq .

# 8. List Services (Should be Stopped)
echo "Listing services..."
curl -s http://localhost:8999/services | jq .

# Cleanup
kill $RUNNER_PID
kill $CONTROLLER_PID
echo "Test Finished"
