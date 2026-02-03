# AI Infra 进阶概念入门指南 (Advanced Concepts Guide)

这份文档为您总结了 **Level 3 (Inference)** 和 **Level 4 (Training)** 的核心技术概念。
所有概念均已在本项目 (`masLambda`) 中通过 Python 脚本进行了仿真验证。

---

## 1. vLLM: 吞吐量之王 (High Throughput Inference)

### 核心痛点

显存是昂贵的稀缺资源。在传统推理中，显存不仅被模型权重占用，还要预留给 KV Cache（上下文记忆）。由于 Sequence Length 也是动态的，传统内存分配会导致大量的**显存碎片 (Fragmentation)**，就像这就好比你在停车场里乱停车，明明有空位，但这辆大车就是停不进去。

### 关键技术: PagedAttention

vLLM 借鉴了操作系统 (OS) 管理内存的思路：

- **如果不连续**：它允许 KV Cache 的显存块是物理不连续的。
- **分页管理**：建立一个“页表 (Page Table)”，把逻辑上连续的 Token 映射到物理上零散的 Block。

### 仿真演示 (`examples/vllm_mock_engine.py`)

- **模拟机制**: `Scheduler` 类。
- **核心行为**: **Continuous Batching (连续批处理)**。
  - 不像传统 Batching 那样必须等这批里最慢的那个人跑完。
  - vLLM 是流水线作业：一旦有一个 Token 生成完毕釋放了 Slot，立马塞进一个新的 Request。
- **效果**: 显存利用率接近 100%，吞吐量提升 2-4 倍。

---

## 2. SGLang: 智力担当 (Structuring & Caching)

### 核心痛点

在 Agent 或多轮对话场景中，我们经常重复发送相同的 Prompt 前缀（System Prompt, Few-Show Examples）。vLLM 每次都要重新计算这些前缀的 KV Cache，非常浪费。

### 关键技术: RadixAttention (前缀树缓存)

SGLang 把 KV Cache 组织成一颗 **Radix Trie (基数树)**。

- **自动复用**: 当新请求进来时，它先在树上匹配。
- **例子**:
  - Req A: `[A, B, C]` -> 计算并存入树。
  - Req B: `[A, B, C, D]` -> 发现 `[A, B, C]` 已经在树上了，直接复用结果，只计算 `[D]`。

### 仿真演示 (`examples/sglang_mock_engine.py`)

- **模拟机制**: `RadixCache` 类。
- **核心行为**: 维护一颗 Token 树。
- **实验结果**:
  - Prompt 1: "The quick brown fox" -> 0% Hit.
  - Prompt 2: "The quick brown fox jumps over" -> **66% Hit**. (Prefill 耗时接近 0)

---

## 3. Distributed Training: 分布式训练 (FSDP / ZeRO)

### 核心痛点

模型越来越大（70B 模型需要 140GB 显存），而单张旗舰卡（H100）只有 80GB。单卡根本装不下。

### 关键技术: ZeRO-3 (Zero Redundancy Optimizer) / FSDP

核心思想是 **"用通信换显存"**。

- **切分 (Sharding)**: 不再让每张卡都存一份完整的模型。而是把模型切成 N 份，每张卡只存 1/N。
- **即时聚合 (All-Gather)**:
  - 当计算需要用到某一层参数时，所有卡立刻通过高速网络（NVLink）互相交换手中的碎片。
  - 拼凑出完整的层 -> 计算 -> **立刻删掉**。
- **代价**: 极高的通信带宽要求。

### 仿真演示 (`examples/fsdp_simulation.py`)

- **DDP模式**: 试图加载 70GB -> 模拟 24GB 显卡 -> **OOM 崩溃**。
- **FSDP模式**: 将 70GB 切分到 8 个进程 -> 每个进程只占 8.75GB -> **成功运行**。

---

## 4. Deep Dive: 核心原理解析 (以通俗比喻为例)

为了帮助加深理解，我们总结了以下两个核心比喻。

### 4.1 vLLM 的 "过山车" 理论 (Continuous Batching)

- **场景**: GPU 计算单元就像一列**过山车**，一次能坐 100 个人 (Batch Size = 100)。
- **Old Way (Static Batching)**:
  - **规则**: 必须凑齐 100 个人才能发车，且所有人必须**同上同下**。
  - **痛点**: 有人只坐 1 分钟（短文本），有人要坐 10 分钟（长文本）。短途游客坐完 1 分钟后，必须在座位上干等 9 分钟（Padding），浪费了 90% 的运力。
- **New Way (Continuous Batching)**:
  - **规则**: **随上随下**。车一直在跑。
  - **机制**: 第 1 分钟有人下车了，空出一个位子，管理员 (Scheduler) 马上让排队的下一个人补上去。
  - **结果**: 每一秒钟，过山车都是**满员运行**的。这就是 vLLM 吞吐量高的秘诀。

### 4.2 Hami vs vLLM: "房东" vs "收纳师"

虽然两者都涉及显存切分，但层级完全不同。

| 角色       | 组件          | 对象         | 职责                         | 比喻                                                                                                                  |
| :--------- | :------------ | :----------- | :--------------------------- | :-------------------------------------------------------------------------------------------------------------------- |
| **房东**   | **Hami** (L2) | **K8s Pod**  | 决定把一张显卡租给几个人用   | 把一套 80平米的房子（A100），隔成两个 40平米的单间，分别租给 Team A 和 Team B。                                       |
| **收纳师** | **vLLM** (L3) | **Requests** | 决定在一个房间里塞进多少东西 | 在 Hami 分给它的 40平米房间里，通过极致的收纳技巧 (PagedAttention)，塞进去原本需要 100平米才能放下的货物（Context）。 |

---

## 5. 总结: 我们的技术栈 (The masLambda Stack)

| 层次               | 核心组件             | 关键技术           | 作用                          |
| :----------------- | :------------------- | :----------------- | :---------------------------- |
| **L4 (Training)**  | `fsdp_simulation.py` | **ZeRO-3**         | 打破单卡显存墙，训练超大模型  |
| **L3.5 (Logic)**   | `sglang_backend`     | **RadixAttention** | 让 Agent 思考更快 (Cache复用) |
| **L3 (Inference)** | `vllm_backend`       | **PagedAttention** | 榨干显卡算力，提高由于吞吐量  |
| **L2 (Control)**   | `Kueue` / `Gateway`  | **Quota/Queue**    | 统一资源调度，防止集群过载    |
| **L1 (Runtime)**   | `Kata Containers`    | **QEMU/Virtio**    | 强隔离沙箱，安全执行代码      |
