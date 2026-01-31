#!/bin/bash
set -e

echo "🚀 Starting KWasm Setup on Kind..."

# 1. Add Helm Repo
echo "📦 Adding KWasm Helm Repo..."
helm repo add kwasm http://kwasm.sh/kwasm-operator/
helm repo update

# 2. Install Operator
echo "🛠️ Installing KWasm Operator..."
helm install -n kwasm --create-namespace kwasm-operator kwasm/kwasm-operator

# 3. Wait for Operator
echo "⏳ Waiting for Operator to be ready..."
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=kwasm-operator -n kwasm --timeout=60s

# 4. Annotate Node (to enable WasmEdge)
echo "🏷️ Annotating Kind nodes to install WasmEdge..."
NODE_NAME=$(kubectl get nodes -o jsonpath='{.items[0].metadata.name}')
kubectl label node $NODE_NAME kwasm.sh/kwasm-node=true --overwrite

echo "⏳ Waiting for WasmEdge installation on node ($NODE_NAME)..."
# In a real scenario, we might wait for a Job or Node status update. 
# For now, we give it a few seconds as the operator ensures the binary is placed.
sleep 5

echo "✅ KWasm Setup Complete! RuntimeClass 'wasm-edge' should be available."
kubectl get runtimeclass
