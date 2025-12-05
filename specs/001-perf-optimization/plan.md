# Implementation Plan - Performance Optimization (Caching & Limits)

Implement Module Caching to speed up cold starts and Resource Limits (Fuel/Memory) to protect the runtime.

## User Review Required

> [!IMPORTANT]
> This change modifies the `WasmRuntime` struct and `execute` method signature. It introduces `sha2` crate for hashing.

## Proposed Changes

### Flash Runner (Rust)

#### [MODIFY] [flash-runner/Cargo.toml](file:///Users/jiwn2/dev/mascreate/masLambda/flash-runner/Cargo.toml)
- Add `sha2` for calculating module hash.
- Add `hex` for string representation of hash.

#### [MODIFY] [flash-runner/src/runtime.rs](file:///Users/jiwn2/dev/mascreate/masLambda/flash-runner/src/runtime.rs)
- **Caching**:
  - Implement `get_or_compile_module` method.
  - Calculate SHA256 hash of `wasm_binary`.
  - Check `module_cache` before compiling.
- **Resource Limits**:
  - Configure `Config::consume_fuel(true)`.
  - Set `Store::add_fuel(N)` before execution.
  - Configure `Config::max_wasm_stack` (optional).

#### [MODIFY] [flash-runner/src/main.rs](file:///Users/jiwn2/dev/mascreate/masLambda/flash-runner/src/main.rs)
- Update `execute` call if signature changes.

## Verification Plan

### Automated Tests
- **Caching Test**: Run the same module twice, assert second run is faster (or check logs for "Cache Hit").
- **Fuel Test**: Run an infinite loop Wasm, assert it returns an error containing "fuel".

### Manual Verification
- Use `test_execution.sh` to verify basic functionality still works.
