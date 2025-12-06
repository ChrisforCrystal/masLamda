use crate::host::HostState;
use anyhow::{Context, Result};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::os::fd::{FromRawFd, IntoRawFd};
use std::sync::{Arc, Mutex};
use wasmtime::{Config, Engine, Linker, Module, Store};

// Wasm 运行时管理器
pub struct WasmRuntime {
    engine: Engine, // Wasmtime 引擎，负责编译和管理模块
    // 模块缓存：Key 是 Wasm 文件的哈希值，Value 是编译好的 Module
    // 使用 Arc<Mutex<...>> 实现线程安全的共享缓存
    module_cache: Arc<Mutex<HashMap<String, Module>>>,
}

impl std::fmt::Debug for WasmRuntime {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("WasmRuntime")
            .field(
                "module_cache_size",
                &self.module_cache.lock().unwrap().len(),
            )
            .finish()
    }
}

impl WasmRuntime {
    // 初始化运行时
    pub fn new() -> Result<Self> {
        let mut config = Config::new();
        config.consume_fuel(true); // 开启 Fuel (燃料) 机制
        config.async_support(true); // 开启异步支持

        let engine = Engine::new(&config)?;
        Ok(Self {
            engine,
            module_cache: Arc::new(Mutex::new(HashMap::new())),
        })
    }

    // 获取或编译模块（核心缓存逻辑）
    fn get_or_compile_module(&self, wasm_binary: &[u8]) -> Result<Module> {
        // 1. 计算 Wasm 二进制文件的 SHA256 哈希
        let mut hasher = Sha256::new();
        hasher.update(wasm_binary);
        let hash = hex::encode(hasher.finalize());

        // 2. 检查缓存是否存在
        {
            let cache = self.module_cache.lock().unwrap();
            if let Some(module) = cache.get(&hash) {
                println!("Cache Hit (命中缓存): {}", hash);
                return Ok(module.clone());
            }
        }

        // 3. 缓存未命中，执行编译（耗时操作）
        println!("Cache Miss (未命中): Compiling {}", hash);
        let module =
            Module::new(&self.engine, wasm_binary).context("Failed to compile Wasm module")?;

        // 4. 存入缓存
        {
            let mut cache = self.module_cache.lock().unwrap();
            cache.insert(hash, module.clone());
        }

        Ok(module)
    }

    // 注册宿主函数 (Host Functions)
    // 注册 Host Functions (宿主函数)
    // 这些函数可以在 Wasm 中被导入并调用，从而扩展 Wasm 的能力 (例如网络请求)
    fn add_host_functions(&self, linker: &mut Linker<WasiHostState>) -> Result<()> {
        // func_wrap2_async: 定义一个接受 2 个参数的异步函数
        // "env": 模块名 (Wasm 中 import 的 module)
        // "http_get": 函数名 (Wasm 中 import 的 name)
        linker.func_wrap2_async(
            "env",
            "http_get",
            // 闭包参数:
            // caller: 调用上下文，可以用来访问 Wasm 内存和 Host State
            // url_ptr, url_len: Wasm 传来的参数 (字符串指针和长度)
            |mut caller: wasmtime::Caller<'_, WasiHostState>, url_ptr: i32, url_len: i32| {
                // 异步 Host Function 需要返回一个 Box<Future>
                Box::new(async move {
                    // 1. 获取 Wasm 内存对象
                    let mem = match caller.get_export("memory") {
                        Some(wasmtime::Extern::Memory(mem)) => mem,
                        _ => return -1, // 错误: 找不到内存导出
                    };

                    // 2. 获取内存数据切片和 Host State
                    // data_and_store_mut 同时借用内存数据和 Store 中的状态
                    let (memory, state) = mem.data_and_store_mut(&mut caller);

                    // 3. 从 Wasm 内存中读取 URL 字符串
                    // memory.get(range) 尝试获取内存的一个切片 (slice)
                    // range 语法: start..end (包含 start，不包含 end)
                    // start = url_ptr (起始地址)
                    // end = url_ptr + url_len (结束地址)
                    // as usize: Rust 中内存索引必须是 usize 类型 (机器字长，32位机是u32，64位机是u64)
                    let url_bytes = match memory.get(url_ptr as usize..(url_ptr + url_len) as usize)
                    {
                        Some(bytes) => bytes,
                        None => return -2, // 错误: 内存访问越界
                    };
                    let url = match std::str::from_utf8(url_bytes) {
                        Ok(s) => s.to_string(),
                        Err(_) => return -3, // 错误: 无效 UTF-8
                    };

                    // 4. 使用 Host State 中的 HTTP Client 发送请求
                    let client = state.host.http_client.clone();

                    match client.get(&url).send().await {
                        Ok(resp) => resp.status().as_u16() as i32, // 返回 HTTP 状态码
                        Err(_) => -4,                              // 错误: 请求失败
                    }
                })
            },
        )?;

        // 注册 http_post 函数
        // 参数: url_ptr, url_len, body_ptr, body_len
        linker.func_wrap4_async(
            "env",
            "http_post",
            |mut caller: wasmtime::Caller<'_, WasiHostState>,
             url_ptr: i32,
             url_len: i32,
             body_ptr: i32,
             body_len: i32| {
                Box::new(async move {
                    // 1. 获取内存
                    let mem = match caller.get_export("memory") {
                        Some(wasmtime::Extern::Memory(mem)) => mem,
                        _ => return -1,
                    };
                    let (memory, state) = mem.data_and_store_mut(&mut caller);

                    // 2. 读取 URL
                    let url = match memory.get(url_ptr as usize..(url_ptr + url_len) as usize) {
                        Some(bytes) => match std::str::from_utf8(bytes) {
                            Ok(s) => s.to_string(),
                            Err(_) => return -3,
                        },
                        None => return -2,
                    };

                    // 3. 读取 Body
                    let body = match memory.get(body_ptr as usize..(body_ptr + body_len) as usize) {
                        Some(bytes) => bytes.to_vec(), // 拷贝为 Vec<u8>
                        None => return -2,
                    };

                    // 4. 发送 POST 请求
                    let client = state.host.http_client.clone();
                    match client.post(&url).body(body).send().await {
                        Ok(resp) => resp.status().as_u16() as i32,
                        Err(_) => -4,
                    }
                })
            },
        )?;
        Ok(())
    }

    // 准备服务模式 (Service Mode) 的运行环境
    // 返回: Store, Instance, LogPath, StdinWriter (Host 写入端), StdoutReader (Host 读取端)
    pub async fn prepare_service(
        &self,
        service_id: &str,
        wasm_binary: &[u8],
        env: HashMap<String, String>, // 新增: 环境变量
    ) -> Result<(
        Store<WasiHostState>,
        wasmtime::Instance,
        String,
        std::fs::File, // Host Stdin Writer (写入端)
        std::fs::File, // Host Stdout Reader (读取端)
    )> {
        let module = self.get_or_compile_module(wasm_binary)?;
        let mut linker = Linker::<WasiHostState>::new(&self.engine);

        // 创建日志文件路径 (仅作参考，实际日志记录由 Host 读取 stdout 完成)
        let log_path = format!("logs/{}.log", service_id);
        std::fs::create_dir_all("logs")?;

        // 设置 Stdin 管道
        // 这是一个类型转换链，目的是将操作系统管道转换为 WASI 可用的输入流

        // 1. 创建原始管道: (读取端, 写入端)
        // stdin_writer: Host 保留，用于写入数据 (Controller -> Runner -> Wasm)
        // stdin_reader: Wasm 使用，用于读取数据
        let (stdin_reader, stdin_writer) = os_pipe::pipe()?;

        // 2. 将管道读取端转换为标准 Rust File 对象
        // 这是中间步骤，因为后续库需要 File 类型
        let stdin_file = unsafe { std::fs::File::from_raw_fd(stdin_reader.into_raw_fd()) };

        // 3. 转换为 cap-std File
        // cap-std 提供基于能力的安全性封装，是 Wasmtime WASI 的要求
        let cap_stdin = cap_std::fs::File::from_std(stdin_file);

        // 4. 转换为 WASI File
        // 这是 Wasmtime 配置上下文最终需要的类型
        let wasi_stdin = wasmtime_wasi::sync::file::File::from_cap_std(cap_stdin);

        // 设置 Stdout 管道
        // Wasm 写入 stdout_writer -> Host 从 stdout_reader 读取
        let (stdout_reader, stdout_writer) = os_pipe::pipe()?;
        let stdout_file = unsafe { std::fs::File::from_raw_fd(stdout_writer.into_raw_fd()) };
        let cap_stdout = cap_std::fs::File::from_std(stdout_file);
        let wasi_stdout = wasmtime_wasi::sync::file::File::from_cap_std(cap_stdout);

        // Stderr 处理：
        // 目前我们将 Stderr 直接写入日志文件，以便记录错误信息。
        // 注意：Stdout 用于 RPC 通信，Stderr 用于日志。
        let log_file = std::fs::File::create(&log_path)?;
        let cap_log = cap_std::fs::File::from_std(log_file);
        let wasi_stderr = wasmtime_wasi::sync::file::File::from_cap_std(cap_log);

        let env_vec: Vec<(String, String)> = env.into_iter().collect();
        let wasi = wasmtime_wasi::tokio::WasiCtxBuilder::new()
            .stdin(Box::new(wasi_stdin))
            .stdout(Box::new(wasi_stdout))
            .stderr(Box::new(wasi_stderr))
            .envs(&env_vec)? // 注入环境变量
            .build();

        let mut store = Store::new(
            &self.engine,
            WasiHostState {
                wasi,
                host: HostState::new(),
            },
        );

        // 服务模式：添加最大 Fuel (资源限制) 以允许长时间运行的服务
        store.add_fuel(u64::MAX)?;

        wasmtime_wasi::tokio::add_to_linker(&mut linker, |s: &mut WasiHostState| &mut s.wasi)?;

        self.add_host_functions(&mut linker)?;

        let instance = linker.instantiate_async(&mut store, &module).await?;

        // 将 os_pipe 句柄转换为 std::fs::File 以便返回给调用者
        // 这里的目的是为了让 Runner (main.rs) 能够方便地使用标准 IO 库来读写这些管道。
        // stdin_writer: Runner 往这里写数据，Wasm 就能从它的 stdin 读到。
        // stdout_reader: Runner 从这里读数据，就能读到 Wasm 往它的 stdout 写的内容。
        // unsafe { ...::from_raw_fd(...) }: 这是因为我们需要直接操作底层文件描述符 (FD) 来进行转换。
        let host_stdin_writer = unsafe { std::fs::File::from_raw_fd(stdin_writer.into_raw_fd()) };
        let host_stdout_reader = unsafe { std::fs::File::from_raw_fd(stdout_reader.into_raw_fd()) };

        Ok((
            store,
            instance,
            log_path,
            host_stdin_writer,
            host_stdout_reader,
        ))
    }

    // 执行 Wasm 模块 (Async)
    pub async fn execute_async(&self, wasm_binary: &[u8], _input: &[u8]) -> Result<String> {
        let module = self.get_or_compile_module(wasm_binary)?;
        let mut linker = Linker::<WasiHostState>::new(&self.engine);

        let stdout = wasi_common::pipe::WritePipe::new_in_memory();
        let stdin = wasi_common::pipe::ReadPipe::from(_input);

        let wasi = wasmtime_wasi::tokio::WasiCtxBuilder::new()
            .stdin(Box::new(stdin))
            .stdout(Box::new(stdout.clone()))
            .inherit_stderr()
            .build();

        let mut store = Store::new(
            &self.engine,
            WasiHostState {
                wasi,
                host: HostState::new(),
            },
        );

        store.add_fuel(10_000)?;

        wasmtime_wasi::tokio::add_to_linker(&mut linker, |s: &mut WasiHostState| &mut s.wasi)?;

        self.add_host_functions(&mut linker)?;

        // Instantiate (Synchronous is fine here as we are not yielding yet)
        // But better to use instantiate_async if we are in async fn
        let instance = linker.instantiate_async(&mut store, &module).await?;

        let func = instance
            .get_typed_func::<(), ()>(&mut store, "_start")
            .or_else(|_| instance.get_typed_func::<(), ()>(&mut store, "main"))
            .context("Could not find _start or main function")?;

        // Call Async
        func.call_async(&mut store, ()).await?;

        drop(store);

        let output_bytes = stdout
            .try_into_inner()
            .expect("sole remaining reference to WritePipe")
            .into_inner();

        let output_str = String::from_utf8(output_bytes).context("Output was not valid UTF-8")?;

        if output_str.is_empty() {
            Ok("Execution completed (No Output)".to_string())
        } else {
            Ok(output_str)
        }
    }
}

// 包含 WASI 上下文和自定义 Host 状态的结构体
pub struct WasiHostState {
    pub wasi: wasmtime_wasi::WasiCtx,
    pub host: HostState,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fuel_limit() {
        /*
        let runtime = WasmRuntime::new().unwrap();
        // Infinite loop: (loop (br 0))
        let wat = r#"(module (func (export "_start") (loop (br 0))))"#;
        let binary = wat::parse_str(wat).unwrap();

        let result = runtime.execute(&binary, &[]);
        assert!(result.is_err());
        let err = result.unwrap_err();
        println!("Error: {:?}", err);
        assert!(format!("{:?}", err).contains("fuel"));
        */
    }
}
