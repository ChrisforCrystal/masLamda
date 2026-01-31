#!/bin/bash
# ----------------------------------------------------
# Script to check if your K8s Node is ready for Kata
# Run this on your K8s Worker Node (Guest OS)
# ----------------------------------------------------

echo "🔍 Checking CPU Virtualization support (Nested Virtualization)..."
CPU_VIRT=$(egrep -c '(vmx|svm)' /proc/cpuinfo)

if [ "$CPU_VIRT" -gt 0 ]; then
    echo "✅ CPU supports Virtualization (vmx/svm found: $CPU_VIRT cores)"
else
    echo "❌ CPU does NOT support Virtualization."
    echo "   Action: You MUST enable 'Nested Virtualization' in VMware settings for this VM."
    echo "   (Right click VM -> Edit Settings -> CPU -> Check 'Expose hardware assisted virtualization')"
    exit 1
fi

echo "----------------------------------------------------"
echo "🔍 Checking KVM Kernel Modules..."

if lsmod | grep -q "kvm"; then
    echo "✅ KVM module is loaded."
else
    echo "⚠️ KVM module NOT loaded."
    echo "   Attempting to load..."
    sudo modprobe kvm
    sudo modprobe kvm-intel 2>/dev/null || sudo modprobe kvm-amd 2>/dev/null
    
    if lsmod | grep -q "kvm"; then
        echo "✅ KVM module loaded successfully."
    else
        echo "❌ Failed to load KVM module. Kata cannot run without it."
        exit 1
    fi
fi

echo "----------------------------------------------------"
echo "🎉 Congratulations! This node is ready for Kata Containers."
echo "   You can now apply the Kata Operator manifests."
