# 深度解析：代码 (TP/PP) 与基础设施 (LWS/Volcano) 的映射关系

很多同学容易在 "Python 代码" 和 "K8s YAML" 之间断片。本文旨在打通这层任督二脉。

## 1. 核心比喻：组建一支足球队 ⚽️

| 角色              | 组件                     | 职责                    | 现实比喻                                                                                                            |
| :---------------- | :----------------------- | :---------------------- | :------------------------------------------------------------------------------------------------------------------ |
| **Volcano/Kueue** | **调度器 (Scheduler)**   | **资源准入 & 帮派调度** | **足协/赛事组委会**。负责确认场地是否空闲，并且必须凑齐 11 个人才能开始比赛。少一个人都不让进场 (Gang Scheduling)。 |
| **LWS**           | **控制器 (Controller)**  | **拓扑管理 (Topology)** | **球队教练**。负责指定谁是队长 (Leader)，谁是队员 (Worker)，并告诉大家队长在哪里 (Service Discovery)。              |
| **TP/PP Code**    | **用户代码 (User Code)** | **实际计算 (Compute)**  | **球员踢球的技术**。比如前锋负责射门 (TP Rank 0)，后卫负责防守 (TP Rank 1)。                                        |

---

## 2. 字段级映射 (Field-Level Mapping)

让我们看看 `tp_demo.py` 里的变量是如何由 `10_lws_vllm.yaml` 注入的。

### A. 谁来决定 Rank? (`RANK`, `WORLD_SIZE`)

在 `tp_demo.py` 中：

```python
rank = int(os.environ["RANK"])
world_size = int(os.environ["WORLD_SIZE"])
```

**在 LWS YAML 中** (`masCompute/10_lws_vllm.yaml`)：
LWS 会自动为每个 Pod 注入这些环境变量：

- LWS 自动设置 `LWS_GROUP_SIZE` -> 代码里的 `WORLD_SIZE`
- LWS 自动设置 `LWS_WORKER_INDEX` -> 代码里的 `RANK` (Leader 是 0, Worker 是 Index+1)

```yaml
# 10_lws_vllm.yaml 片段
leaderWorkerTemplate:
  size: 2 # <--- 这就是 WORLD_SIZE = 2
  leaderTemplate:
    # ... Leader 默认为 Rank 0
  workerTemplate:
    # ... Worker 自动获得 index 1, 2, ...
```

### B. 谁来告诉它是哪张卡? (`flavor-h100`)

我们的代码需要跑在特定的硬件上。

**在 Kueue/Volcano 中**：

```yaml
# 10_lws_vllm.yaml 片段
kueue.x-k8s.io/resource-flavor: flavor-h100 # <--- 调度器保证这组 Pod 只能跑在 H100 节点上
```

这保证了当 Python 代码执行 `torch.cuda.is_available()` 时，它看到的是 H100 而不是 A10。

### C. 怎么找到队友? (`MASTER_ADDR`)

在 `tp_demo.py` 中：

```python
os.environ['MASTER_ADDR'] = 'localhost' # 本地测试写死
```

**在生产环境 (LWS) 中**：
LWS 会自动创建一个 Headless Service 指向 Leader Pod，并注入环境变量：

```yaml
# 10_lws_vllm.yaml 中的 command
command:
  - sh
  - -c
  - |
    # LWS 魔法：LWS_LEADER_ADDRESS 是由控制器自动填写的 DNS 域名
    export MASTER_ADDR=${LWS_LEADER_ADDRESS} 
    python3 -m vllm.entrypoints.openai.api_server ...
```

---

## 3. 完整数据流 (The Big Picture)

1.  **提交 YAML**: 你 `kubectl apply -f 10_lws_vllm.yaml`。
2.  **Volcano 介入**: 发现你需要 `size: 2` (2 个 Pod)。它检查集群里是否有 2 张空闲的 H100。
    - _如果有_: 同时也锁住这 2 张卡 (Gang Scheduling)。
    - _如果没有_: 2 个 Pod 都处于 Pending 状态（谁也别想偷跑）。
3.  **LWS 介入**: start Pods。
    - 启动 Pod-0 (Leader): 注入 `RANK=0`, `MASTER_ADDR=pod-0.dns`
    - 启动 Pod-1 (Worker): 注入 `RANK=1`, `MASTER_ADDR=pod-0.dns`
4.  **Python 代码运行**:
    - Pod-0 里的 `tp_demo.py` 启动，监听 `MASTER_ADDR:PORT`。
    - Pod-1 里的 `tp_demo.py` 启动，连接 `MASTER_ADDR:PORT`。
    - **握手成功 (Handshake)** -> 开始训练/推理。

## 总结

你写的 `tp_demo.py` 是 **"做什么" (What)**。
LWS 和 Volcano 是 **"在哪里做" (Where)** 和 **"怎么组织" (How)**。

它们通过 **环境变量 (Environment Variables)** 进行交接。
