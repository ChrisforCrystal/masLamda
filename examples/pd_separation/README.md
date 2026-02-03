# PD Separation 验证包

## 📦 包结构

```
examples/pd_separation/
├── __init__.py          # 包初始化
├── engine.py            # 推理引擎 (模拟 vLLM)
├── client.py            # 并发客户端测试
├── launcher.py          # 一键启动脚本
└── README.md            # 本文档
```

## 🎯 验证目标

通过本地 CPU 环境完整验证 Prefill-Decode 分离架构，包括：

- ✅ Leader-Worker 拓扑管理
- ✅ NCCL 分布式通信
- ✅ Continuous Batching 调度
- ✅ PD 流水线协作

## 🚀 一步步验证流程

### 步骤 0: 环境准备

确保在项目根目录：

```bash
cd /Users/jiwn2/dev/masallsome/masLambda
```

确认依赖已安装：

```bash
pip install fastapi uvicorn requests torch
```

### 步骤 1: 启动验证系统

运行启动器：

```bash
python -m examples.pd_separation.launcher
```

**预期输出：**

```text
============================================================
   PD Separation 验证系统启动
============================================================

[步骤 1/4] 启动 Prefill 集群...
🚀 启动 Prefill Leader...
🚀 启动 Prefill Worker...

[步骤 2/4] 启动 Decode 集群...
🚀 启动 Decode Leader...
🚀 启动 Decode Worker...

[步骤 3/4] 等待集群初始化（5秒）...

[步骤 4/4] 检查集群健康状态...
✅ Prefill 和 Decode 集群均已就绪!

============================================================
   开始并发测试
============================================================
```

### 步骤 2: 观察并发测试结果

系统会自动运行 5 个并发请求，观察输出：

```text
👤 [User-1] Sending Request...
👤 [User-2] Sending Request...
👤 [User-3] Sending Request...
👤 [User-4] Sending Request...
👤 [User-5] Sending Request...
✅ [User-1] Finished in 0.52s. Result: ... batch-0 done
✅ [User-2] Finished in 0.53s. Result: ... batch-1 done
...
⏱️ Total Wall Time for 5 Users: 0.55s
```

**关键验证点：**

- ✅ 所有 5 个用户都成功完成
- ✅ 总时间应接近单个请求时间（说明 Batching 生效）
- ✅ 结果中包含 "batch-X done"（说明服务端成功处理批次）

### 步骤 3: 查看日志（可选）

如果测试失败，检查日志文件：

```bash
# 查看 Prefill 集群日志
cat prefill_leader.log
cat prefill_worker.log

# 查看 Decode 集群日志
cat decode_leader.log
cat decode_worker.log
```

### 步骤 4: 停止系统

测试完成后，按 `Enter` 键停止所有服务：

```text
按 Enter 键停止所有服务...

🛑 停止所有进程...
✅ 所有进程已停止
```

## 🔧 故障排查

### 问题 1: Connection refused

**现象：** `❌ 集群启动失败`

**原因：** 端口被占用或进程启动失败

**解决：**

```bash
# 检查端口占用
lsof -i :8000
lsof -i :8001

# 杀死僵尸进程
pkill -f "pd_separation.engine"
```

### 问题 2: KeyError 或 Bad Response

**现象：** `❌ [User-X] Bad Response: {...}`

**原因：** 服务端逻辑错误

**解决：**

```bash
# 查看详细错误
cat prefill_leader.log | grep -A 10 "Error"
```

### 问题 3: NCCL 初始化超时

**现象：** 日志中显示 `torch.distributed timeout`

**原因：** 防火墙阻止本地端口通信

**解决：**

```bash
# macOS 临时关闭防火墙
sudo pfctl -d
```

## 📚 相关文档

- [架构设计文档](../../docs/pd_separation_design.md)
- [完整验证指南](../../docs/pd_separation_verification.md)
- [LWS YAML 配置](../../masCompute/10_lws_vllm.yaml)
