# 实施计划: 微服务 API (SpecKit)

## 目标
通过基于 Stdin/Stdout 的 JSON-RPC 协议，使 Wasm 服务能够作为交互式微服务运行。

## 需要用户评审
> [!IMPORTANT]
> 此变更需要对 `flash-runner` 的并发模型进行重大更新，以处理与 Wasm 服务的全双工通信。

## 提议的变更

### 1. 协议与 SDK
- [ ] 创建一个可复用的 Rust 结构体/辅助工具，以便 Wasm 服务轻松实现 "循环-读取-分发-写入" 模式。
- [ ] 创建一个使用此模式的 `calculator.wasm` 示例进行验证。

### 2. Flash Runner (Rust)
- [ ] 更新 `ServiceInstance` 以保存:
  - `stdin_sender`: 用于写入 Wasm `stdin`。
  - `response_channels`: 一个 `Arc<Mutex<HashMap<String, oneshot::Sender<String>>>>`，用于将请求 ID 映射到等待的调用者。
- [ ] 修改 `prepare_service` / `execute_async`:
  - 不再仅仅记录 `stdout`，而是分流数据流:
    - 以 `{` (JSON) 开头的行 -> 尝试解析为 RPC 响应 -> 触发回调。
    - 其他行 -> 记录到文件 (保持现有的日志行为)。
- [ ] 实现 `InvokeService` gRPC 方法:
  - 生成 ID。
  - 注册回调通道。
  - 将 JSON 写入 Wasm `stdin`。
  - 等待回调通道 (带超时)。

### 3. Flash Controller (Go)
- [ ] 更新 `runner.proto` 添加 `InvokeService`。
- [ ] 实现 `POST /services/:id/invoke` 端点。

### 4. Dashboard (前端)
- [ ] 添加一个 "调用 (Invoke)" 界面 (类似 Postman/Swagger UI) 来测试运行中服务的方法。

## 验证计划
1. **部署 `calculator.wasm`**。
2. **调用 `add` 方法**:
   ```bash
   curl -X POST http://localhost:8999/services/<id>/invoke \
     -d '{"method": "add", "params": {"a": 5, "b": 10}}'
   ```
3. **期望响应**: `{"result": 15}`。
