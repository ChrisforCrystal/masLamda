# PD Separation 验证包使用指南

## 快速开始

本验证包展示了 Prefill-Decode 分离架构的完整工作流程。

### 一键运行

```bash
# 在项目根目录执行
python -m examples.pd_separation.launcher
```

### 验证成功标志

看到以下输出说明验证通过：

```
✅ Prefill 和 Decode 集群均已就绪!
✅ [User-1] Finished in 0.5Xs. Result: ... batch-0 done
```

## 包内容说明

| 文件          | 说明         | 对应架构组件        |
| ------------- | ------------ | ------------------- |
| `engine.py`   | 推理引擎实现 | vLLM AsyncLLMEngine |
| `client.py`   | 并发客户端   | 压力测试工具        |
| `launcher.py` | 系统启动器   | 部署脚本            |

## 详细文档

请查看 [README.md](./README.md) 获取完整的步骤说明和故障排查指南。
