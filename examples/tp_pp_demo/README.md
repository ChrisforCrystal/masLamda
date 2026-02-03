# TP & PP 分布式训练 Demo

这套 Demo 演示了 AI 大模型训练中两个最核心的并行技术：**张量并行 (TP)** 和 **流水线并行 (PP)**。
代码经过简化，使用了 PyTorch 原生的 `Distributed` 库 (Gloo backend)，可以直接在 Mac/CPU 上运行，无需 GPU。

## 1. 目录结构

```
examples/tp_pp_demo/
├── tp_demo.py    # 张量并行演示 (Tensor Parallelism)
├── pp_demo.py    # 流水线并行演示 (Pipeline Parallelism)
└── README.md     # 本文档
```

## 2. 核心概念

### 张量并行 (TP) - `tp_demo.py`

**解决单卡显存不足以存下整个权重的问题。**

- 原理：将一个大的 Linear 层 ($Y=XW$) 的权重 $W$ 竖着切开 (Column Parallel)。
- 过程：
  - Rank 0 存左半边 $W_1$，算 $Y_1 = XW_1$
  - Rank 1 存右半边 $W_2$，算 $Y_2 = XW_2$
  - 最后用 `All-Gather` 把 $Y_1, Y_2$ 拼起来。

### 流水线并行 (PP) - `pp_demo.py`

**解决模型层数太多，单卡放不开的问题。**

- 原理：将模型横着切开。
- 过程：
  - Rank 0 负责 Layer 1-2 (Stage 1)
  - Rank 1 负责 Layer 3-4 (Stage 2)
  - 数据流：Rank 0 算完 -> `Send` -> Rank 1 接收 -> Rank 1 算完。

## 3. 运行指南

请在项目根目录运行以下命令：

### 运行 TP Demo

```bash
torchrun --nproc_per_node=2 examples/tp_pp_demo/tp_demo.py
```

_预期输出：你会看到两个进程分别计算 Partial Result，最后 Rank 0 打印出完整的 Gather 结果。_

### 运行 PP Demo

```bash
torchrun --nproc_per_node=2 examples/tp_pp_demo/pp_demo.py
```

_预期输出：你会看到 "Rank 0 Sending" 和 "Rank 1 Received" 的日志交互。_

### 运行 互动式推理 Demo (Inference)

**这是模拟真实服务：Master 接收用户输入 -> 广播 -> 集体计算**

```bash
# 注意：现在需要启动 3 个进程 (1 Master + 2 Workers)
torchrun --nproc_per_node=3 examples/tp_pp_demo/tp_inference.py
```

_操作：Rank 0 (Master) 等待输入 -> 广播给 Rank 1,2 -> Rank 1,2 计算 -> Rank 1 发回结果给 Master_

### 运行 PP Bubble Demo (流水线气泡可视化)

**这个 Demo 演示为什么 PP 效率不是 100%：你会看到明显的等待时间 (Idle Time)**

```bash
# 启动 3 个 Stage (Rank 0 -> Rank 1 -> Rank 2)
torchrun --nproc_per_node=3 examples/tp_pp_demo/pp_bubble.py
```

_预期观察：程序会模拟计算延迟。请观察日志的时间戳，Rank 2 在开始时需要空等 Rank 0 和 Rank 1 (Fill Phase)，而 Rank 0 在结束前早早没事干了 (Drain Phase)。_
