use anyhow::Result;
use runner::runner_service_server::{RunnerService, RunnerServiceServer};
use runner::{
    DeployRequest, DeployResponse, ExecuteRequest, ExecuteResponse, InvokeRequest, InvokeResponse,
    ListRequest, ListResponse, ServiceInfo, StopRequest, StopResponse,
};
use serde_json::json;
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::sync::{mpsc, oneshot};
use tonic::{transport::Server, Request, Response, Status};

// 引入生成的 gRPC 代码
pub mod runner {
    tonic::include_proto!("runner");
}

mod host;
mod runtime;
mod service_manager;

use runtime::WasmRuntime;
use service_manager::ServiceManager;

// Runner 服务结构体，持有 Wasm 运行时环境
#[derive(Debug)]
pub struct MyRunner {
    // 使用 Arc (原子引用计数) 实现线程安全的共享运行时
    runtime: Arc<WasmRuntime>,
    service_manager: Arc<Mutex<ServiceManager>>,
}

impl MyRunner {
    // 初始化 Runner，创建 Wasm 运行时
    pub fn new() -> Result<Self> {
        Ok(Self {
            runtime: Arc::new(WasmRuntime::new()?),
            service_manager: Arc::new(Mutex::new(ServiceManager::new())),
        })
    }
}

// 实现 gRPC 服务接口
#[tonic::async_trait]
impl RunnerService for MyRunner {
    // 处理执行请求的核心函数 (FaaS Mode)
    async fn execute(
        &self,
        request: Request<ExecuteRequest>,
    ) -> Result<Response<ExecuteResponse>, Status> {
        let req = request.into_inner();
        let start = std::time::Instant::now();

        // 直接调用异步执行函数
        // 注意：如果 Wasm 代码是 CPU 密集型的且不让出控制权，可能会阻塞 Tokio 线程
        // 但我们在 runtime 中开启了 Fuel 限制，所以最终会返回
        let result = self
            .runtime
            .execute_async(&req.wasm_binary, &req.input_data)
            .await;

        let duration = start.elapsed().as_nanos() as i64;

        match result {
            Ok(output) => Ok(Response::new(ExecuteResponse {
                output_data: output.into_bytes(),
                error: "".to_string(),
                execution_time_ns: duration,
            })),
            Err(e) => {
                let err_msg = format!("{:?}", e);
                println!("Sending Error Response: {}", err_msg);
                Ok(Response::new(ExecuteResponse {
                    output_data: vec![],
                    error: err_msg,
                    execution_time_ns: duration,
                }))
            }
        }
    }

    // 部署长运行服务 (Service Mode)
    // 流程:
    // 1. 接收 Wasm 二进制文件
    // 2. 准备运行环境 (编译 Wasm, 创建管道)
    // 3. 创建通信通道 (Stdin Channel, Response Channels)
    // 4. 启动后台异步任务 (Tokio Task) 来运行 Wasm
    // 5. 在后台任务中，启动两个子任务:
    //    - Stdin Task: 从 Channel 读取数据写入 Wasm 的 Stdin 管道
    //    - Stdout Task: 从 Wasm 的 Stdout 管道读取数据，解析 JSON-RPC 响应，并发送回 Response Channel
    // 6. 将服务实例保存到 ServiceManager
    async fn deploy_service(
        &self,
        request: Request<DeployRequest>,
    ) -> Result<Response<DeployResponse>, Status> {
        let req = request.into_inner();
        let runtime = self.runtime.clone();
        let service_manager_for_task = self.service_manager.clone();
        let service_manager = self.service_manager.clone();
        let service_id = uuid::Uuid::new_v4().to_string();
        let id_clone = service_id.clone();

        // 1. 准备环境 (编译 + 实例化 + 管道)
        let (mut store, instance, log_path, stdin_file, stdout_file) = runtime
            .prepare_service(&service_id, &req.wasm_binary)
            .await
            .map_err(|e| Status::internal(e.to_string()))?;

        // 创建通道
        // stdin_tx: 用于向 Wasm 发送数据 (Controller -> Runner -> Wasm)
        // stdin_rx: Wasm 接收端 (在后台任务中使用)
        let (stdin_tx, stdin_rx) = std::sync::mpsc::channel::<String>();

        // response_channels: 用于存储每个请求的响应通道 (Request ID -> Oneshot Sender)
        // 当 Wasm 返回响应时，Stdout Task 会根据 ID 找到对应的 Sender 将结果发回
        let response_channels: Arc<Mutex<HashMap<String, oneshot::Sender<String>>>> =
            Arc::new(Mutex::new(HashMap::new()));
        let response_channels_clone = response_channels.clone();

        // 转换文件句柄 (注意：Stdout 读取器需要保持为 std::fs::File 以便在阻塞线程中使用，Stdin 现在也是)
        // let mut stdin_file = tokio::fs::File::from_std(stdin_file); // 保持为 std::fs::File
        // let stdout_file = tokio::fs::File::from_std(stdout_file); // 保持为 std::fs::File
        let log_path_clone = log_path.clone();
        let service_id_clone = service_id.clone();

        // 2. 启动异步任务运行 Wasm 和 IO 处理
        let handle = tokio::spawn(async move {
            println!("Service {} started", id_clone);

            // 启动 IO 任务
            // 使用 std::thread 处理 Stdin，避免异步管道问题
            // 启动 IO 任务: Stdin 处理线程
            // 这是一个独立的 OS 线程 (std::thread)，专门负责往 Wasm 的 Stdin 管道里写数据。
            // 为什么用独立线程？因为管道写入可能会阻塞，如果用 Tokio 的异步任务，
            // 一旦阻塞可能会卡死整个 Runtime 的调度器。
            std::thread::spawn(move || {
                use std::io::Write;
                let mut stdin_file = stdin_file; // 这是连接到 Wasm Stdin 的管道写入端

                // 循环接收来自 Controller 的消息 (通过 stdin_rx 通道)
                // recv() 是阻塞的，直到有新消息发过来
                while let Ok(msg) = stdin_rx.recv() {
                    // 调试日志: 记录准备写入的内容
                    {
                        if let Ok(mut f) = std::fs::OpenOptions::new()
                            .create(true)
                            .append(true)
                            .open("runner_debug.log")
                        {
                            writeln!(f, "Stdin Task: Writing to pipe: {}", msg.trim()).unwrap();
                        }
                    }

                    // 1. 写入数据: 将字符串转换为字节并写入管道
                    if let Err(e) = stdin_file.write_all(msg.as_bytes()) {
                        eprintln!("Failed to write to Wasm stdin: {}", e);
                        break; // 写入失败 (可能 Wasm 挂了)，退出循环
                    }

                    // 2. 刷新缓冲区: 确保数据立刻被发送，而不是停留在缓冲区里
                    // 这对于交互式通信非常重要！
                    if let Err(e) = stdin_file.flush() {
                        eprintln!("Failed to flush Wasm stdin: {}", e);
                        break;
                    }

                    // 调试日志: 记录写入完成
                    {
                        if let Ok(mut f) = std::fs::OpenOptions::new()
                            .create(true)
                            .append(true)
                            .open("runner_debug.log")
                        {
                            writeln!(f, "Stdin Task: Flushed").unwrap();
                        }
                    }
                }
            });
            // 启动处理 Stdout 的任务 (从 Wasm 读取)
            let response_channels_clone_2 = response_channels_clone.clone();
            // 使用 std::thread 避免管道的异步文件问题
            std::thread::spawn(move || {
                // 我们需要以阻塞模式打开文件。
                // 因为我们有文件描述符，所以可以直接使用它。
                // 注意：stdout_file 保持为 std::fs::File，没有转换为 Tokio 文件。

                use std::io::{BufRead, BufReader, Write};

                let mut reader = BufReader::new(stdout_file);

                // 打开日志文件用于追加 (阻塞模式)
                let mut log_file = std::fs::OpenOptions::new()
                    .create(true)
                    .append(true)
                    .open(&log_path_clone)
                    .unwrap_or_else(|e| {
                        eprintln!("Failed to open log file: {}", e);
                        panic!("Failed to open log file");
                    });

                println!("Stdout task started for service {}", service_id_clone);

                for line in reader.lines() {
                    match line {
                        Ok(line) => {
                            println!("Received line from service {}: {}", service_id_clone, line);

                            // 调试日志
                            {
                                if let Ok(mut f) = std::fs::OpenOptions::new()
                                    .create(true)
                                    .append(true)
                                    .open("runner_debug.log")
                                {
                                    writeln!(f, "Stdout Task: Received line: {}", line).unwrap();
                                }
                            }

                            // 记录到文件
                            let _ = log_file.write_all(format!("{}\n", line).as_bytes());

                            // 尝试解析为 JSON-RPC 响应
                            // Wasm 输出的每一行都可能是日志，也可能是 RPC 响应。
                            // 我们尝试把它解析成 JSON，看里面有没有 "id" 字段。
                            if let Ok(json) = serde_json::from_str::<serde_json::Value>(&line) {
                                if let Some(id_val) = json.get("id") {
                                    if let Some(id) = id_val.as_str() {
                                        println!("Found RPC response for request {}", id);

                                        // 关键逻辑: 响应路由 (Response Routing)
                                        // 1. 锁住 response_channels 字典
                                        let mut channels =
                                            response_channels_clone_2.lock().unwrap();

                                        // 2. 根据 ID 查找并移除对应的发送端 (Sender)
                                        // 为什么是 remove？因为 Oneshot Channel 只能用一次，用完就销毁。
                                        if let Some(tx) = channels.remove(id) {
                                            // 3. 发送响应给等待的 gRPC 线程
                                            // tx.send() 会唤醒正在 invoke_service 里 await 的那个请求线程
                                            let _ = tx.send(line.clone());
                                            println!("Sent response to channel for request {}", id);
                                        } else {
                                            // 如果找不到 ID，说明可能超时了，或者 ID 错了
                                            println!("No channel found for request {}", id);
                                        }
                                    }
                                }
                            }
                        }
                        Err(e) => {
                            eprintln!("Error reading stdout: {}", e);
                            break;
                        }
                    }
                }
                println!("Stdout task ended for service {}", service_id_clone);
            });

            // 获取入口函数
            let func = instance
                .get_typed_func::<(), ()>(&mut store, "_start")
                .or_else(|_| instance.get_typed_func::<(), ()>(&mut store, "main"));

            if let Ok(func) = func {
                // 异步调用 Wasm
                if let Err(e) = func.call_async(&mut store, ()).await {
                    println!("Service {} error/interrupted: {:?}", id_clone, e);
                }
            } else {
                println!("Service {} failed to find entry point", id_clone);
            }
            println!("Service {} finished", id_clone);

            // 4. 更新服务状态
            // 当代码执行到这里时，说明 Wasm 实例已经运行结束了 (可能是正常退出，也可能是报错崩溃)
            // 我们需要通知 ServiceManager 把这个服务的状态标记为 "Stopped"。
            // 这样下次再有请求发过来，invoke_service 检查状态时就会知道服务已经不在运行了，从而拒绝请求。
            let mut manager = service_manager_for_task.lock().unwrap();
            manager.update_status(&id_clone, "Stopped");
        });

        // 3. 保存 AbortHandle 和 Channels
        // 5. 注册服务实例
        // 这里我们把 response_channels 存进了 ServiceManager。
        // 注意：此时 response_channels 是空的 (HashMap::new())。
        //
        // 它的数据是从哪里来的？
        // 当 invoke_service 被调用时 (有请求来了)，它会：
        // 1. 从 ServiceManager 里拿出这个 response_channels 的引用。
        // 2. 往里面插入一个 (RequestID, Sender)。
        // 3. 然后在这里启动的那个后台线程 (Stdout Task) 就能读到这个 Sender，把结果发回去。
        //
        // 这就是 "共享状态" (Shared State) 的魔法：
        // deploy_service 创建容器 -> 存入 Manager -> invoke_service 往容器里塞信道 -> 后台线程从容器里取信道
        let abort_handle = handle.abort_handle();
        {
            let mut manager = service_manager.lock().unwrap();
            manager.add_service(
                service_id.clone(),
                abort_handle,
                log_path,
                stdin_tx,
                response_channels,
            );
        }

        Ok(Response::new(DeployResponse {
            service_id,
            error: "".to_string(),
        }))
    }

    // 停止服务
    async fn stop_service(
        &self,
        request: Request<StopRequest>,
    ) -> Result<Response<StopResponse>, Status> {
        let req = request.into_inner();
        let service_manager = self.service_manager.clone();

        let result = {
            let mut manager = service_manager.lock().unwrap();
            manager.stop_service(&req.service_id)
        };

        match result {
            Ok(_) => Ok(Response::new(StopResponse {
                success: true,
                error: "".to_string(),
            })),
            Err(e) => Ok(Response::new(StopResponse {
                success: false,
                error: e,
            })),
        }
    }

    // 列出服务
    async fn list_services(
        &self,
        _request: Request<ListRequest>,
    ) -> Result<Response<ListResponse>, Status> {
        let service_manager = self.service_manager.lock().unwrap();
        let services = service_manager
            .list_services()
            .into_iter()
            .map(|s| ServiceInfo {
                service_id: s.id,
                status: s.status,
            })
            .collect();

        Ok(Response::new(ListResponse { services }))
    }

    // 获取服务日志
    async fn get_logs(
        &self,
        request: Request<runner::GetLogsRequest>,
    ) -> Result<Response<runner::GetLogsResponse>, Status> {
        let req = request.into_inner();
        let service_manager = self.service_manager.lock().unwrap();

        let logs = service_manager
            .get_logs(&req.service_id)
            .unwrap_or_else(|_| "".to_string());

        Ok(Response::new(runner::GetLogsResponse {
            logs,
            error: "".to_string(),
        }))
    }

    // 调用服务方法
    // 流程:
    // 1. 根据 Service ID 查找服务实例
    // 2. 检查服务状态 (必须是 Running)
    // 3. 获取通信通道 (Stdin Sender, Response Channels)
    // 4. 创建本次请求的响应通道 (Oneshot Channel) 并注册到 Response Channels Map
    // 5. 构造 JSON-RPC 请求
    // 6. 通过 Stdin Sender 发送请求给 Wasm
    // 7. 等待 Wasm 通过 Response Channel 返回结果
    async fn invoke_service(
        &self,
        request: Request<InvokeRequest>,
    ) -> Result<Response<InvokeResponse>, Status> {
        let req = request.into_inner();

        // 调试日志
        {
            use std::io::Write;
            if let Ok(mut f) = std::fs::OpenOptions::new()
                .create(true)
                .append(true)
                .open("runner_debug.log")
            {
                writeln!(f, "Invoke Service: {}", req.service_id).unwrap();
            }
        }

        let (stdin_sender, response_channels) = {
            let service_manager = self.service_manager.lock().unwrap();
            let service = service_manager
                .services
                .get(&req.service_id)
                .ok_or(Status::not_found("Service not found"))?;

            if service.status != "Running" {
                return Err(Status::failed_precondition(format!(
                    "Service is not running (status: {})",
                    service.status
                )));
            }

            let stdin_sender = service
                .stdin_sender
                .as_ref()
                .ok_or(Status::internal("Service has no stdin"))?
                .clone();
            let response_channels = service.response_channels.clone();
            (stdin_sender, response_channels)
        };

        // 创建响应通道
        // 4. 创建响应通道 (Oneshot Channel)
        // 这是一个 "一次性" 的通道，专门用于接收 *这一个* 请求的响应。
        // tx (Sender): 我们把它放进 response_channels 里，给后台线程用。
        // rx (Receiver): 我们自己拿着，在这里死等 (await) 结果。
        //
        // 为什么每次都要新建？
        // 因为每个 invoke 请求都是独立的，我们需要把每个请求的响应精确地匹配回来。
        // 用完这一次，这个通道就废弃了。
        let (tx, rx) = oneshot::channel();
        let req_id = uuid::Uuid::new_v4().to_string();

        {
            let mut channels = response_channels.lock().unwrap();
            channels.insert(req_id.clone(), tx);
        }

        // 构造 JSON-RPC 请求
        // 注意：params 已经是来自请求的 JSON 字符串
        let params_json: serde_json::Value = serde_json::from_str(&req.params)
            .map_err(|e| Status::invalid_argument(format!("Invalid params JSON: {}", e)))?;

        let rpc_req = json!({
            "jsonrpc": "2.0",
            "id": req_id,
            "method": req.method,
            "params": params_json
        });

        let req_str = rpc_req.to_string();
        // 调试日志
        {
            use std::io::Write;
            if let Ok(mut f) = std::fs::OpenOptions::new()
                .create(true)
                .append(true)
                .open("runner_debug.log")
            {
                writeln!(f, "Sending to Wasm: {}", req_str).unwrap();
            }
        }

        // 发送给 Wasm
        stdin_sender
            .send(req_str + "\n")
            .map_err(|_| Status::internal("Failed to send to Wasm"))?;

        // 等待响应
        // TODO: 添加超时处理
        let response_line = rx
            .await
            .map_err(|_| Status::internal("Response channel closed"))?;

        // 调试日志
        {
            use std::io::Write;
            if let Ok(mut f) = std::fs::OpenOptions::new()
                .create(true)
                .append(true)
                .open("runner_debug.log")
            {
                writeln!(f, "Received from Wasm: {}", response_line).unwrap();
            }
        }

        // 解析响应以提取结果
        let response_json: serde_json::Value = serde_json::from_str(&response_line)
            .map_err(|_| Status::internal("Invalid JSON response from Wasm"))?;

        if let Some(error) = response_json.get("error") {
            if !error.is_null() {
                return Ok(Response::new(InvokeResponse {
                    result: "".to_string(),
                    error: error.to_string(),
                }));
            }
        }

        let result = response_json
            .get("result")
            .map(|v| v.to_string())
            .unwrap_or_default();

        Ok(Response::new(InvokeResponse {
            result,
            error: "".to_string(),
        }))
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // 简单的文件日志记录器
    let log_file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open("runner_debug.log")?;
    let log_file = Arc::new(Mutex::new(log_file));

    let log = move |msg: String| {
        let mut f = log_file.lock().unwrap();
        use std::io::Write;
        writeln!(f, "Log: {}", msg).unwrap();
    };

    let log_clone = log.clone(); // 用于 RunnerService

    let addr = "127.0.0.1:50051".parse()?;
    // 将日志记录器传递给 Runner (需要修改结构体，但为了快速调试，也许直接使用 println 即可)
    // 或者更好的是使用全局日志记录器，或者直接在方法中写入文件。

    // 我们直接在方法中使用文件写入来记录日志。

    println!("Flash Runner (Rust) 正在监听: {}", addr);

    // 启动 gRPC 服务器
    Server::builder()
        .add_service(
            RunnerServiceServer::new(MyRunner::new()?)
                .max_decoding_message_size(50 * 1024 * 1024)
                .max_encoding_message_size(50 * 1024 * 1024),
        )
        .serve(addr)
        .await?;

    Ok(())
}
