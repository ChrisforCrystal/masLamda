# AI Infrastructure 进阶学习路线图 (The Road to AI Arch)

恭喜您！目前您已经掌握了 **“云原生底座 (Cloud Native Foundation)”** 的核心能力：

- **计算隔离**: Kata/Firecracker (如何安全地跑代码)
- **资源调度**: Kueue/K8s (如何分蛋糕)
- **镜像交付**: Nydus/OverlayFS (如何送快递)

在工程化 AI Infra 领域，接下来还有四座大山需要翻越。这也是目前大厂（OpenAI, Meta, 字节, 阿里）最稀缺的技能树。

---

## Level 3: 推理引擎优化 (Inference Optimization)

_只跑起来不够，要跑得快、吞吐量大。_

- **核心痛点**: GPU 显存昂贵，如何让一张卡跑并发更多的请求？
- **关键技术点**:
  1.  **显存管理**: 深度理解 **PagedAttention (vLLM)** 原理。它像操作系统管理内存页一样管理 KV Cache，彻底解决了显存碎片化问题。
  2.  **调度策略**: **Continuous Batching (连续批处理)**。不再等整个 Batch 跑完才返回，而是跑完一个 Token 就进去一个新的，流水线拉满。
  3.  **计算加速**: **TensorRT-LLM** / **FlashAttention**。理解为什么 CUDA Kernel 这么写能快 10 倍。
- **练手项目**:
  - 在您的 `masLambda` 里集成一个 vLLM Worker。
  - 尝试手写一个简单的 Python 版 PagedAttention 模拟器。

## Level 4: 分布式训练架构 (Distributed Training Arch)

_单卡跑不下了，需要几千张卡一起跑。_

- **核心痛点**: 通信墙 (Communication Wall)。卡多了，时间全花在卡间通信上了。
- **关键技术点**:
  1.  **3D 并行**:
      - **Data Parallel (DP/DDP/FSDP)**: 数据切分，模型复制。
      - **Tensor Parallel (TP)**: 模型切分（切层内），卡间通信极频繁。
      - **Pipeline Parallel (PP)**: 模型切分（切层间），流水线作业。
  2.  **集合通信**: 理解 **NCCL** (AllReduce, AllGather) 是怎么工作的。
- **练手项目**:
  - 使用 PyTorch FSDP 微调一个 Llama3-8B 模型。
  - 抓取 NCCL 通信日志，分析带宽利用率。

## Level 5: 高性能网络 (HPC Networking)

_以太网 TCP/IP 已经跟不上了。_

- **核心痛点**: 内核协议栈太慢，CPU 忙不过来。
- **关键技术点**:
  1.  **RDMA (远程直接内存访问)**: 绕过 CPU，网卡直接读写远程内存。
  2.  **RoCE v2 vs InfiniBand**: 两种主流的高速网络物理协议。
  3.  **GPU Direct**: 网卡直接把数据塞进显存，不经过 CPU 内存。
- **学习建议**: 这个领域硬件门槛高，建议以阅读论文和厂商白皮书（NVIDIA Docs）为主。

## Level 6: AI 专用存储 (AI Storage)

_Checkpoints 动辄几百 GB，Loading 动辄几 TB 小文件。_

- **核心痛点**: 传统的 NAS/S3 撑不住千万级的 IOPS。
- **关键技术点**:
  1.  **缓存层**: **JuiceFS** / **Alluxio**。利用节点本地 NVMe SSD 做分布式缓存。
  2.  **Checkpointing**: **Async Checkpoint**。训练时不停车，后台异步存盘。
- **练手项目**:
  - 部署 JuiceFS，对比它和直接读 S3 的小文件训练速度差异。

---

## 建议的学习顺序

**Inference (vLLM) -> Training (FSDP) -> Storage (JuiceFS) -> Networking (RDMA)**

结合您现在的 `masLambda` 项目，**Inference Optimization** 是最顺理成章的下一步。您可以考虑把现在的简单 Python Worker 升级为支持 vLLM 的高性能推理节点。
