# PD 分离 (Prefill-Decode Separation) 架构设计

在 LLM 推理中，**Prefill (阅读理解)** 和 **Decode (逐字生成)** 是两个性质截然不同的阶段。

## 1. 核心矛盾

| 特征         | Prefill (首字生成/阅读)                                                   | Decode (后续生成/写作)                         |
| :----------- | :------------------------------------------------------------------------ | :--------------------------------------------- |
| **计算类型** | **Compute Bound (算力密集)**                                              | **Memory Bound (显存带宽密集)**                |
| **操作**     | 一次性处理几千个 Token 的矩阵乘法                                         | 每次只处理 1 个 Token，但要搬运巨大的 KV Cache |
| **最佳硬件** | **H100 / A100** (算力强，Tensor Core 多)                                  | **L40S / A10** (便宜，带宽性价比高)            |
| **问题**     | 如果混用同一种卡，Decode 阶段那昂贵的 H100 算力都在**空转等待显存数据**。 |

## 2. 解决方案：拆分！(Disaggregation)

我们把服务拆成两组不同的 Instance：

1.  **Prefill Pool (P-Instance)**: 全是 **H800**。只负责快速读完 Prompt，生成 KV Cache。
2.  **Decode Pool (D-Instance)**: 全是 **L40S**。接手 KV Cache，慢慢吐字。

![PD Split](https://mermaid.ink/img/pako:eNpVkLFOwzAQhl_F-kwg0QkS0wWJlYGBgYFQlS_nXBJXjuzLqSrKdyfNUAXb_v_T_Xf-C2qTAyXoem_fLKE9vBoJz-dp-TyfLxbz2SLN5_Mk_S_9K_M_YI_W0e7QO1gMrI12jX6Gj_740cEKe4-xQ0tD52C06Rqc48Z7fIET9gMGD-uN_gE3OOCEdwNqY1LKyikpZZmXmVeFzMsiz0tfrMrqXZZFUeZFXpS3Mv_I6yIt86LI82_Zl4VclmleZHl-y4osy7TMy6IoizSveJ5Nq1b-Az0yP1k?type=png)

(注: 架构图与 RDMA 类似，因为本质依赖高速互联)

## 3. 关键技术挑战：KV Cache 传输

当 P-Instance 算完后，它手里的 KV Cache (可能几百 MB) 必须**瞬间**传给 D-Instance。
如果走 TCP 网络，传输时间 > 节省下来的算力时间，得不偿失。

**必须使用 RDMA/RoCE 网络**！
只有 RDMA 能在几毫秒内把几百 MB 数据从一台机器的显存搬到另一台机器的显存。

## 4. 实战架构 (K8s + Ray)

我们将创建 `masCompute/08_pd_separation_cluster.yaml`，包含：

- **Ray Worker Group A (Prefill)**:
  - Resource: `nvidia.com/gpu: 1` (A100)
  - Queue: `team-search-prefill`
- **Ray Worker Group B (Decode)**:
  - Resource: `nvidia.com/gpu: 1` (A10)
  - Queue: `team-search-decode`

上层 Gateway 负责路由：先发给 A，拿到 ID 后发给 B。
