# Agent Resource Control Guide (Day 2 Operations)

为了确保 Agent 沙箱在生产环境下的安全运行，防止恶意代码或逻辑错误（如死循环、内存泄漏）拖垮整个集群，我们需要在 Kubernetes 和 Kata 层面实施严格的资源控制。

本文档详细介绍了针对 **CPU、内存、存储、网络** 和 **生命周期** 的五维控制策略。

---

## 1. 计算资源 (CPU & Memory)

Kata 的优势在于它支持 **Hotplug (热插拔)**。

### 1.1 静态限制 (Kubernetes Requests/Limits)

这是最基础的防线。Kata Shim 会读取这些值并配置 QEMU。

- **Requests**: 决定 Pod 被调度到哪个节点，以及 QEMU 启动时的初始规格。
- **Limits**: 决定 QEMU 如果超用会被宿主机杀掉（OOMKill），或者由 Guest 内核进行流控。

```yaml
resources:
  requests:
    cpu: "500m" # 初始分配 0.5 核
    memory: "512Mi" # 初始分配 512MB
  limits:
    cpu: "2" # 最大允许突发到 2 核
    memory: "2Gi" # 最大允许使用 2GB
```

### 1.2 动态热插拔 (Kata Hotplug)

当 Agent 的负载超过 requests 但小于 limits 时，Kata 会动态向 VMM 插入虚拟 CPU 和内存条。

> **注意**: 为了支持热插拔，Pod 的 QoS 类型最好设置为 **Burstable** (即 requests < limits)。如果是 Guaranteed (requests == limits)，QEMU 启动时就会预占所有资源，无法享受按需扩展的优势。

---

## 2. 存储资源 (Storage)

Agent 在运行时通常需要写临时文件（如生成的代码文件、下载的数据集）。

### 2.1 临时目录限制 (EmptyDir SizeLimit)

Agent 默认对 rootfs 是只读的，写操作通常在 `/tmp` 或 `/workspace`。必须限制其大小，防止 Agent 填满宿主机磁盘。

```yaml
volumes:
  - name: workspace
    emptyDir:
      sizeLimit: "1Gi" # 严格限制临时空间不超过 1GB
```

### 2.2 挂载传播 (No Propagation)

为了安全起见，绝对禁止开启 `mountPropagation: Bidirectional`，防止 Agent 在 VM 内的挂载操作影响宿主机。

---

## 3. 网络资源 (Network)

Agent 代码通常是不可信的，通过网络渗出数据的风险极高。

### 3.1 NetworkPolicy (白名单模式)

默认拒绝所有出站流量，只允许访问必要的服务（如 Gateway API, PyPI, HuggingFace）。

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: agent-allow-whitelist
spec:
  podSelector:
    matchLabels:
      app: agent-sandbox
  policyTypes: [Egress]
  egress:
    - to:
        - ipBlock: { cidr: 0.0.0.0/0 }
      ports:
        - port: 443 # 仅允许 HTTPS
        - port: 53 # 仅允许 DNS
```

### 3.2 带宽限制 (Traffic Shaping)

通过 CNI 插件（如 Calico 或 Cilium）的 annotation 限制带宽。

```yaml
metadata:
  annotations:
    kubernetes.io/egress-bandwidth: "10M"
    kubernetes.io/ingress-bandwidth: "10M"
```

---

## 4. 进程与生命周期 (Lifecycle)

### 4.1 进程数限制 (PID Limit)

防止 Fork Bomb (无限创建子进程)。
在 Kubernetes 1.20+ 可以直接设置：

```yaml
spec:
  pidsLimit: 100 # 限制该 Pod 最多只能有 100 个进程
```

### 4.2 执行超时 (ActiveDeadlineSeconds)

防止 Agent 任务卡死或进入死循环无限期占用资源。

```yaml
spec:
  activeDeadlineSeconds: 3600 # 1小时后必须强制终止
```

---

## 5. 安全上下文 (SecurityContext)

虽然有 VM 隔离，但仍需遵循容器安全最佳实践。

```yaml
securityContext:
  allowPrivilegeEscalation: false
  runAsUser: 1000 # 禁止以 root 运行
  runAsGroup: 3000
  runAsNonRoot: true
  readOnlyRootFilesystem: true # 根文件系统只读
  capabilities:
    drop: ["ALL"] # 丢弃所有 Linux Capability
```
