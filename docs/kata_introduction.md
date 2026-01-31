# Kata Containers 入门指南 (Kata 101)

## 1. 什么是 Kata Containers?

简单一句话：**Kata 让你的容器像虚拟机一样安全，同时像容器一样快。**

- **外观 (Look)**: 它看起来像个 Docker 容器。你可以用 `kubectl` 管理它，用 docker 镜像跑它。
- **内核 (Core)**: 它其实是个轻量级虚拟机 (MicroVM)。

### 为什么需要它？

传统的容器 (如 Docker/RunC) 是**共享内核**的。

- 如果我在容器里运行恶意代码 (比如 `rm -rf /`)，或者利用内核漏洞提权，我可能直接攻破宿主机。
- 对于 AI Agent 这种**运行不可信代码**的场景，传统容器就像是在"裸奔"，非常危险。

Kata 给每个容器发了一个独立的内核 (Guest Kernel)。哪怕由于漏洞导致内核崩溃，崩的也只是它自己的小虚拟机，宿主机毫发无损。

---

## 2. 架构对比 (The Architecture)

```mermaid
graph TD
    subgraph "Standard Container (Docker/RunC)"
        App1[App 1]
        App2[App 2]
        Kernel[Host Kernel (Shared!) 😱]
        App1 --> Kernel
        App2 --> Kernel
    end

    subgraph "Kata Container"
        subgraph "Pod 1 (MicroVM)"
            KApp1[App 1]
            GuestKernel1[Guest Kernel 🛡️]
            KApp1 --> GuestKernel1
        end
        subgraph "Pod 2 (MicroVM)"
            KApp2[App 2]
            GuestKernel2[Guest Kernel 🛡️]
            KApp2 --> GuestKernel2
        end
        Hypervisor[Hypervisor (QEMU/Cloud Hypervisor)]
        HostKernel[Host Kernel]

        GuestKernel1 --> Hypervisor
        GuestKernel2 --> Hypervisor
        Hypervisor --> HostKernel
    end
```

---

## 3. 核心组件 (Under the Hood)

当您在 K8S 里创建一个 Kata Pod 时，发生了什么？

1.  **Containerd**: K8S 通知 Containerd 要创建容器。
2.  **Shim v2**: Containerd 调用 Kata 的 Shim (垫片)。
3.  **Hypervisor**: Kata 启动一个 Hypervisor (通常是 QEMU 或 Cloud Hypervisor)。
4.  **Guest OS**: 启动一个极小的 Linux 内核 (几百毫秒)。
5.  **Agent**: 虚拟机里有个小 Agent，负责接收指令启动您的 Docker 镜像。

---

## 4. 如何使用？(Usage)

非常简单，只需要改一个字段：`runtimeClassName`。

**标准容器 YAML**:

```yaml
spec:
  containers:
    - image: nginx
```

**Kata 容器 YAML**:

```yaml
spec:
  runtimeClassName: kata-qemu # <--- 就是加了这一行
  containers:
    - image: nginx
```

## 5. 总结 (Summary)

| 特性         | 标准容器 (RunC)           | Kata Containers                        |
| :----------- | :------------------------ | :------------------------------------- |
| **隔离级别** | 进程级 (Namespace/Cgroup) | **虚拟机级 (Hardware Virtualization)** |
| **安全性**   | 中 (共享内核风险)         | **高 (独占内核)**                      |
| **启动速度** | 极快 (毫秒)               | 快 (几百毫秒)                          |
| **资源开销** | 极低                      | 低 (约 100MB 内存底噪)                 |
| **最佳场景** | Web 服务, 微服务          | **多租户, AI Sandbox, CI/CD**          |

这就是 Kata。它是云原生时代为了解决"不信任代码"而生的终极防线。
