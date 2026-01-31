#!/bin/bash
set -e

echo "🚀 Starting Kata Containers Installation..."

# 1. Apply RBAC (Permissions for the Operator)
echo "🔒 Applying RBAC..."
kubectl apply -f https://raw.githubusercontent.com/kata-containers/kata-containers/main/tools/packaging/kata-deploy/kata-rbac/base/kata-rbac.yaml

# 2. Deploy Kata-Deploy (This is the heavy lifter)
# It's a DaemonSet that runs on every node and installs the Kata binaries/kernel.
echo "📦 Deploying Kata binaries to nodes (DaemonSet)..."
kubectl apply -f https://raw.githubusercontent.com/kata-containers/kata-containers/main/tools/packaging/kata-deploy/kata-deploy/base/kata-deploy.yaml

# 3. Create RuntimeClasses
# This is what makes 'runtimeClassName: kata-qemu' vaild.
echo "📝 Registering RuntimeClasses (kata-qemu, kata-clh)..."
kubectl apply -f https://raw.githubusercontent.com/kata-containers/kata-containers/main/tools/packaging/kata-deploy/runtimeclasses/kata-runtimeClasses.yaml

echo "--------------------------------------------------------"
echo "⏳ Installation triggered! It may take a few minutes."
echo "   The 'kata-deploy' pod needs to download the VM image and Kernel."
echo ""
echo "👉 Check status with: kubectl -n kube-system get pods -l name=kata-deploy"
echo "👉 Once 'Running', you can use: runtimeClassName: kata-qemu"
echo "--------------------------------------------------------"
