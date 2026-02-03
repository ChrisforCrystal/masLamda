# AI Infra 高性能网络指南 (HPC Networking Guide)

在分布式训练 (Distributed Training) 中，**计算**往往不是瓶颈，**通信**才是。
当您用 4 张 H100 训练一个 70B 模型时，这 4 张卡之间每秒钟要交换数百 GB 的梯度数据。如果网络跟不上，显卡就会闲置等待。

本文为您解析 Kubernetes 环境下支撑高性能 AI 训练的四大金刚：**RDMA, RoCE, NVLink, NCCL**。

---

## 1. 物理层：怎么连接？(NVLink vs RDMA)

### 1.1 NVLink / NVSwitch (卡间互联)

- **场景**: 一般仅限于**单机内部**（Intra-Node）。
- **作用**: 让 8 张 GPU 像连体婴儿一样工作，显寸共享。
- **带宽**: 900 GB/s (H100 NVLink 4.0)。远超 PCIe Gen5 (128 GB/s)。
- **K8s 配置**: 通常不需要额外 YAML，依赖 **Hami** 或 NVIDIA Driver 的拓扑透传。

### 1.2 RDMA (远程直接内存访问)

- **场景**: **多机之间**（Inter-Node）。
- **原理**: 允许一台机器的网卡直接读写另一台机器的内存，**完全绕过 CPU 和 内核**。
- **对比**:
  - **TCP/IP (传统)**: 数据 memcpy 到内核 -> 封包 -> 发送。延迟高，CPU 负载高。
  - **RDMA**: 网卡 DMA 直接搬运。延迟 < 1us，CPU 0% 介入。

### 1.3 RoCE v2 (RDMA over Converged Ethernet)

- **定义**: 在普通以太网上跑 RDMA 协议。是目前 AI 数据中心（包括阿里云、腾讯云）的主流方案。
- **要求**: 网卡支持 (ConnectX-5/6/7)，交换机支持 (PFC 流控)。

---

## 2. 软件层：怎么调度？(NCCL & Multus)

### 2.1 NCCL (NVIDIA Collective Communication Library)

- **定义**: NVIDIA 官方的通信原语库（Gather, Scatter, All-Reduce）。
- **智能**: 它会自动探测硬件。
  - 发现有 NVLink，就走 NVLink。
  - 发现有 RDMA 网卡，就走 RDMA。
  - 啥都没有，就走慢速的 Socket (TCP)。
- **关键环境变量**:
  - `NCCL_P2P_DISABLE=1`: 强制关掉 P2P (调试用)。
  - `NCCL_IB_HCA=mlx5`: 指定走哪张 RDMA 网卡。
  - `NCCL_DEBUG=INFO`: 打印通信日志。

### 2.2 Multus CNI (双网卡支持)

- **痛点**: K8s 默认每个 Pod 只有一张网卡 (eth0)，通常走 Overlay网络 (Flannel/Calico)，会有封包损耗，且不支持 RDMA。
- **解法**: **Multus CNI** 允许给 Pod 插第二张、第三张网卡。
  - **eth0**: 走 K8s 网络，负责 API Server 通信、日志、心跳。
  - **net1**: 走 **Macvlan/HostDevice**，直通物理 RDMA 网卡，专门跑 NCCL 数据。

---

## 3. 实战配置架构

在 `masCompute` 中，我们将这样落实：

1.  **基础设施**: 部署 Multus CNI 插件。
2.  **网络定义 (`07_hpc_network.yaml`)**: 定义一个叫 `rdma-net` 的网络附件。
3.  **应用配置 (`04_ray_cluster.yaml`)**:
    - 给 Ray Worker 加上 `k8s.v1.cni.cncf.io/networks: rdma-net` 注解。
    - 注入 `NCCL_*` 环境变量。

![Architecture](https://mermaid.ink/img/pako:eNpVkLFOwzAQhl_F-kwg0QkS0wWJlYGBgYFQlS_nXBJXjuzLqSrKdyfNUAXb_v_T_Xf-C2qTAyXoem_fLKE9vBoJz-dp-TyfLxbz2SLN5_Mk_S_9K_M_YI_W0e7QO1gMrI12jX6Gj_740cEKe4-xQ0tD52C06Rqc48Z7fIET9gMGD-uN_gE3OOCEdwNqY1LKyikpZZmXmVeFzMsiz0tfrMrqXZZFUeZFXpS3Mv_I6yIt86LI82_Zl4VclmleZHl-y4osy7TMy6IoizSveJ5Nq1b-Az0yP1k?type=png)
