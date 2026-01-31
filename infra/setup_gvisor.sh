#!/bin/bash
set -e

NODE_NAME=${1:-kind-control-plane}

echo "🚀 Starting gVisor (runsc) Installation on Kind Node: $NODE_NAME..."

# 1. 在 Kind 节点（Docker 容器）内部安装 runsc
# 我们使用 'docker exec' 在节点内部运行命令
# 1. 在 Kind 节点（Docker 容器）内部安装 runsc
# 我们使用 'docker exec' 在节点内部运行命令
echo "📦 Downloading runsc binary..."

# 检测架构 (宿主机是 arm64，Kind 节点也是 arm64)
ARCH=$(uname -m)
URL_ARCH=""
if [ "$ARCH" = "x86_64" ]; then
  URL_ARCH="x86_64"
elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
  URL_ARCH="aarch64"
else
  echo "❌ Unsupported Architecture: $ARCH"
  exit 1
fi

echo "Detected Architecture: $URL_ARCH"

docker exec $NODE_NAME sh -c "
  rm -f /usr/local/bin/containerd-shim-runsc-v1 && \
  # 下载 gVisor 核心二进制文件 (runsc)
  curl -L https://storage.googleapis.com/gvisor/releases/release/latest/$URL_ARCH/runsc -o /usr/local/bin/runsc-bin && \
  # 下载 containerd shim (用于连接 containerd 和 gVisor)
  curl -L https://storage.googleapis.com/gvisor/releases/release/latest/$URL_ARCH/containerd-shim-runsc-v1 -o /usr/local/bin/containerd-shim-runsc-v1 && \
  chmod +x /usr/local/bin/runsc-bin /usr/local/bin/containerd-shim-runsc-v1 && \
  
  # [关键点 1] 创建包装脚本以强制使用 ptrace 平台
  echo '#!/bin/sh' > /usr/local/bin/runsc && \
  echo 'exec /usr/local/bin/runsc-bin --platform=ptrace \"\$@\"' >> /usr/local/bin/runsc && \
  chmod +x /usr/local/bin/runsc
"

# 2. 配置 Containerd 使用 runsc
echo "⚙️ Configuring Containerd shim..."
docker exec $NODE_NAME sh -c '
  cat <<EOF > /etc/containerd/runsc.toml
version = 2
[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runsc]
  runtime_type = "io.containerd.runsc.v1"
EOF
'

# 注意：Kind 使用特定的 containerd 配置结构。
# 我们需要修补 config.toml。理想情况下我们使用 "kind create cluster --config"，但对于现有集群我们需要修补。

docker exec $NODE_NAME sh -c '
  # 备份配置
  cp /etc/containerd/config.toml /etc/containerd/config.toml.bak
  
  # [关键点 2] 注册 Runtime 配置
  # 原理：Kubernetes只知道 RuntimeClass 的名字（如 "gvisor"），它会将这个名字传给 Containerd。
  # Containerd 需要知道如何处理名为 "runsc" 的请求。
  # 我们在 config.toml 中添加一段映射：[plugins...runtimes.runsc]，指定 runtime_type 为 "io.containerd.runsc.v1"。
  # 这样 Containerd 收到 "runsc" 请求时，就会调用我们刚刚下载的 shim 二进制文件。
  if ! grep -q "runsc" /etc/containerd/config.toml; then
    cat <<EOF >> /etc/containerd/config.toml

[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runsc]
  runtime_type = "io.containerd.runsc.v1"
EOF
  fi
  
  # [关键点 3] 重启生效
  # 原理：Containerd 是一个常驻守护进程，它只在启动时读取一次配置文件。
  # 修改了磁盘上的 config.toml 后，必须重启服务，让它重新加载配置，
  # 才能识别出我们新注册的 "runsc" 运行时。
  systemctl restart containerd
'

echo "✅ gVisor (runsc) installed on $NODE_NAME!"
echo "---------------------------------------------------"
echo "👉 Next Step: Apply RuntimeClass manifest."
