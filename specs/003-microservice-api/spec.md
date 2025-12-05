# 微服务 API 规范 (SpecKit 模式)

## 1. 概述
为了将 Wasm 服务转变为真正的微服务，我们需要一种标准的协议来让它们暴露方法并处理请求。鉴于 Wasmtime 14 的网络功能限制，我们将使用 **标准输入/输出 (Stdin/Stdout)** 作为通信通道。

这种模式允许 Wasm 服务作为一个长运行的 "Reactor" (反应堆) 运行，它监听 `stdin` 上的 JSON 命令，并在 `stdout` 上输出 JSON 响应。

## 2. 协议定义

我们将使用基于 **JSON Lines (NDJSON)** 的简化版 **JSON-RPC 2.0** 风格协议。

### 2.1 通信通道
- **输入**: Wasm 进程的 `stdin`。
- **输出**: Wasm 进程的 `stdout`。
- **格式**: 每个请求和响应必须是一行有效的 JSON，以换行符 (`\n`) 结尾。

### 2.2 请求格式 (Controller -> Wasm)
```json
{
  "jsonrpc": "2.0",
  "id": "unique_request_id",
  "method": "method_name",
  "params": { "key": "value" }
}
```
- `id`: 由 Controller 生成的唯一字符串 ID，用于跟踪请求。
- `method`: 要调用的 Wasm 服务内的函数名称。
- `params`: 包含参数的 JSON 对象。

### 2.3 响应格式 (Wasm -> Controller)
**成功:**
```json
{
  "jsonrpc": "2.0",
  "id": "unique_request_id",
  "result": { "data": "..." }
}
```

**错误:**
```json
{
  "jsonrpc": "2.0",
  "id": "unique_request_id",
  "error": {
    "code": 123,
    "message": "错误描述"
  }
}
```

## 3. 架构变更

### 3.1 Flash Runner (Rust)
- **Service Manager (服务管理器)**:
  - 必须持有一个可写入的 Wasm 进程 `stdin` 句柄。
  - 必须在一个独立的异步任务中监控 Wasm 进程的 `stdout`。
  - **消息分发器**: 一种机制，用于将 `stdout` 响应中的 `id` 映射回发起调用的挂起 gRPC 请求。
    - 使用 `HashMap<String, Sender<Result>>` 来存储挂起的请求。

### 3.2 Flash Controller (Go)
- **新 API**: `POST /services/:id/invoke`
  - Body: `{ "method": "...", "params": ... }`
  - 行为:
    1. 生成请求 ID。
    2. 调用 Runner 的 `InvokeService` gRPC 方法。
    3. 等待响应。
    4. 将结果返回给 HTTP 客户端。

### 3.3 Wasm Service (Rust SDK)
- 需要一个辅助循环 (Helper Loop)，执行以下操作:
  1. 从 `stdin` 读取一行。
  2. 解析 JSON。
  3. 根据 `method` 分发到注册的处理函数。
  4. 将结果序列化为 JSON。
  5. 将 JSON 行打印到 `stdout`。

## 4. 示例流程
1. **用户** 发送 `POST /services/123/invoke`，内容为 `{ "method": "add", "params": {"a": 1, "b": 2} }`。
2. **Controller** 调用 Runner gRPC `Invoke("123", "add", params)`。
3. **Runner** 生成 ID `req_1`，将 `{"id":"req_1", "method":"add", ...}\n` 写入 Wasm `stdin`。
4. **Wasm** 读取行，计算 `1+2=3`，打印 `{"id":"req_1", "result": 3}\n`。
5. **Runner** 拦截该行，找到挂起的请求 `req_1`，用 `3` 完成 gRPC 调用。
6. **Controller** 返回 `200 OK { "result": 3 }`。
