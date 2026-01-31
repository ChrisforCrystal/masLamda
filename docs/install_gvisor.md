# gVisor (Runsc) 集成指南

Master，既然您选择了 **gVisor** 作为首选沙箱方案，这里是详细的集成指南。

---

## 1. 架构原理

gVisor 通过拦截容器内的所有系统调用 (Syscall)，在用户态内核 (Sentry) 中进行模拟，从而防止恶意代码攻击宿主机内核。

- **RuntimeClass**: `gvisor`
- **Handler**: `runsc`

---

## 2. 安装步骤 (针对 K8S 节点)

我们需要在每个 K8S Worker 节点上安装 `runsc` 和 `containerd-shim-runsc-v1`。

### 自动化脚本

您可以直接使用项目中的 `infra/setup_gvisor.sh`：

```bash
# 在您的 Gateway 机器上运行 (假设能访问 Kind/K8S)
./infra/setup_gvisor.sh <node-name>
```

### 手动安装 (如果不使用脚本)

在每个节点上执行：

```bash
# 1. 下载二进制
wget https://storage.googleapis.com/gvisor/releases/release/latest/x86_64/runsc
wget https://storage.googleapis.com/gvisor/releases/release/latest/x86_64/containerd-shim-runsc-v1
chmod +x runsc containerd-shim-runsc-v1
mv runsc containerd-shim-runsc-v1 /usr/local/bin/

# 2. 配置 Containerd (/etc/containerd/config.toml)
# 添加如下配置:
[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runsc]
  runtime_type = "io.containerd.runsc.v1"
```

---

## 3. 核心坑点：KVM vs Ptrace

这是您在 VMware 环境中可能遇到的最大问题。

- **默认模式 (KVM)**: gVisor 默认使用 KVM 平台加速。这要求您的宿主机支持虚拟化 (即便它是 VM)。
  - **要求**: `check_kata_readiness.sh` 检测通过 (CPU 支持 vmx/svm)。
- **降级模式 (Ptrace/Systrap)**: 如果您的环境**不支持**嵌套虚拟化 (check 失败)，`runsc` 会启动失败。
  - **解决**: 强制使用 `ptrace` 平台。
  - **方法**: 创建一个包装脚本覆盖默认行为。

```bash
# /usr/local/bin/runsc (Wrapper Script)
#!/bin/sh
exec /usr/local/bin/runsc-bin --platform=ptrace "$@"
```

_(我们的 `setup_gvisor.sh` 已经为您处理了这个逻辑，如果检测不到 KVM 可能会尝试自动降级)_

---

## 4. 如何使用

安装完成后，应用 `RuntimeClass`：

```yaml
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: gvisor
handler: runsc
```

然后在 Pod 中指定：

```yaml
spec:
  runtimeClassName: gvisor
  containers: ...
```
