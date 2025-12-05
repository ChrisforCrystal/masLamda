# 项目宪法 (Project Constitution)

1. **架构模式**: 必须采用 Monorepo (单体仓库) 结构。
   - `flash-controller/`: 控制面，使用 Go 语言 (Gin + gRPC)。
   - `flash-runner/`: 数据面，使用 Rust 语言 (Tokio + Tonic + Wasmtime)。
   - `proto/`: 存放 .proto 协议定义文件。

2. **通信协议**:
   - 组件间通信**必须**使用 gRPC。
   - 禁止使用 HTTP JSON 进行内部通信。

3. **代码规范**:
   - Go: 使用标准项目布局，错误处理必须规范。
   - Rust: 必须使用 async/await 异步编程，追求高性能和零拷贝。

4. **文档**: 所有生成的代码必须包含清晰的注释。