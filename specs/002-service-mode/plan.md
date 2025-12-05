# 实现计划: Wasm 服务模式 (Reactor)

本计划详细说明了如何实现 Wasm 服务的长运行支持 (Reactor 模式)。

## 1. 核心概念验证 (PoC)

- [ ] **创建无限循环 Wasm**: 编写 `infinite.wat`，包含一个死循环和 `sleep`，用于模拟长运行服务。
- [ ] **验证 Runner 行为**: 确认当前的 Runner 在执行死循环 Wasm 时是否会阻塞线程或超时。

## 2. Flash Runner 改造 (Rust)

- [ ] **异步运行时升级**: 确保 `wasmtime` 配置支持异步调用 (`Config::async_support(true)`)。
- [ ] **服务管理器 (ServiceManager)**:
    - 创建 `ServiceManager` 结构体，用于管理所有运行中的服务实例。
    - 使用 `HashMap<String, ServiceInstance>` 存储服务状态。
- [ ] **后台执行**: 修改 `execute` 逻辑，使其能在后台线程（或 Tokio 任务）中运行 Wasm，不阻塞主线程。
- [ ] **停止机制**: 实现 `stop_service(id)`，通过 `Wasmtime` 的 `Store::interrupt_handle` 或取消 Context 来强制停止 Wasm。

## 3. Flash Controller 改造 (Go)

- [ ] **新增 API**:
    - `POST /services/deploy`: 接收 Wasm 文件，通知 Runner 启动服务，返回 Service ID。
    - `POST /services/:id/stop`: 通知 Runner 停止服务。
    - `GET /services`: 列出所有正在运行的服务。
- [ ] **状态同步**: 定期从 Runner 获取服务列表（或通过心跳），更新 Controller 的状态视图。

## 4. 验证与测试

- [ ] **生命周期测试**:
    1. 部署 `infinite.wat` -> 返回 ID。
    2. 查询列表 -> 显示 "Running"。
    3. 停止服务 -> 显示 "Stopped"。
    4. 再次查询 -> 服务消失或状态更新。
- [ ] **并发测试**: 同时部署 5 个 `infinite.wat`，确认它们都能同时运行。

## 5. 风险与缓解

- **资源泄露**: 长运行服务可能耗尽内存。
    - *缓解*: 在 Runner 中为每个实例设置内存上限 (`Store::limiter`)。
- **僵尸进程**: Runner 崩溃后服务状态不一致。
    - *缓解*: Controller 重启后应重新同步 Runner 状态。
