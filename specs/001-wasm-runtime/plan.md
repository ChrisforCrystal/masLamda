# Implementation Plan - Wasm Serverless Runtime Core

Implement the core Wasm runtime using Wasmtime in Rust (`flash-runner`) and a basic control plane in Go (`flash-controller`).

## User Review Required

> [!IMPORTANT]
> This plan introduces `wasmtime` as the core execution engine. Ensure the environment supports building Wasmtime (requires C compiler).

## Proposed Changes

### Protocol Definitions

#### [NEW] [proto/runner.proto](file:///Users/jiwn2/dev/mascreate/masLambda/proto/runner.proto)
- Define `RunnerService` with `Execute` method.
- Define `ExecuteRequest` (wasm_binary, input_data) and `ExecuteResponse` (output, error).

### Flash Runner (Rust)

#### [MODIFY] [flash-runner/Cargo.toml](file:///Users/jiwn2/dev/mascreate/masLambda/flash-runner/Cargo.toml)
- Add `reqwest` for HTTP host functions.
- Add `anyhow` for error handling.

#### [NEW] [flash-runner/src/runtime.rs](file:///Users/jiwn2/dev/mascreate/masLambda/flash-runner/src/runtime.rs)
- Implement `WasmRuntime` struct.
- Initialize `wasmtime::Engine` and `Linker`.
- Implement `execute` method:
  - Compile module (with caching).
  - Instantiate.
  - Call `_start` or exported function.

#### [NEW] [flash-runner/src/host.rs](file:///Users/jiwn2/dev/mascreate/masLambda/flash-runner/src/host.rs)
- Define host functions for `wasmtime`.
- Implement `http_get` function using `reqwest`.

#### [MODIFY] [flash-runner/src/main.rs](file:///Users/jiwn2/dev/mascreate/masLambda/flash-runner/src/main.rs)
- Start gRPC server implementing `RunnerService`.
- Delegate execution to `WasmRuntime`.

### Flash Controller (Go)

#### [MODIFY] [flash-controller/main.go](file:///Users/jiwn2/dev/mascreate/masLambda/flash-controller/main.go)
- Setup Gin router.
- Add `/run` endpoint to trigger execution via gRPC.

## Verification Plan

### Automated Tests
- **Unit Test**: Test `WasmRuntime` with a simple Wasm module (embedded bytes).
- **Integration Test**: Start `flash-runner`, send gRPC request from `flash-controller` or `grpcurl`.

### Manual Verification
- Compile a "Hello World" Wasm (Rust/TinyGo).
- Upload/Run via `flash-controller` API.
