use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use tokio::task::AbortHandle;

#[derive(Debug, Clone)]
pub struct ServiceInstance {
    pub id: String,
    pub status: String, // "Running", "Stopped"
    pub abort_handle: Option<AbortHandle>,
    pub log_path: String,
    pub stdin_sender: Option<std::sync::mpsc::Sender<String>>,
    pub response_channels: Arc<Mutex<HashMap<String, tokio::sync::oneshot::Sender<String>>>>,
}

#[derive(Debug)]
pub struct ServiceManager {
    pub services: HashMap<String, ServiceInstance>,
}

impl ServiceManager {
    pub fn new() -> Self {
        Self {
            services: HashMap::new(),
        }
    }

    pub fn add_service(
        &mut self,
        id: String,
        handle: AbortHandle,
        log_path: String,
        stdin_sender: std::sync::mpsc::Sender<String>,
        response_channels: Arc<Mutex<HashMap<String, tokio::sync::oneshot::Sender<String>>>>,
    ) {
        self.services.insert(
            id.clone(),
            ServiceInstance {
                id,
                status: "Running".to_string(),
                abort_handle: Some(handle),
                log_path,
                stdin_sender: Some(stdin_sender),
                response_channels,
            },
        );
    }

    // 停止服务
    // 核心逻辑是利用 Tokio 的 AbortHandle 来强制取消异步任务
    pub fn stop_service(&mut self, id: &str) -> Result<(), String> {
        if let Some(service) = self.services.get_mut(id) {
            // 1. 取出 AbortHandle (take() 会把 Option 变成 None，防止重复停止)
            if let Some(handle) = service.abort_handle.take() {
                // 2. 发送取消信号
                // 这会导致对应的 tokio::spawn 任务立即收到一个 Cancelled 错误并停止运行
                // 就像拔掉了 Wasm 虚拟机的电源
                handle.abort();

                // 3. 更新状态
                service.status = "Stopped".to_string();
                return Ok(());
            }
            // 如果 handle 已经是 None，说明可能之前已经停止了，或者任务自然结束了
            // 我们只需要确保状态是 Stopped 即可
            service.status = "Stopped".to_string();
            return Ok(());
        }
        Err("Service not found".to_string())
    }

    pub fn update_status(&mut self, id: &str, status: &str) {
        if let Some(service) = self.services.get_mut(id) {
            service.status = status.to_string();
        }
    }

    pub fn list_services(&self) -> Vec<ServiceInstance> {
        self.services.values().cloned().collect()
    }

    pub fn get_logs(&self, id: &str) -> Result<String, String> {
        if let Some(service) = self.services.get(id) {
            match std::fs::read_to_string(&service.log_path) {
                Ok(logs) => return Ok(logs),
                Err(e) => return Ok(format!("Failed to read logs: {}", e)),
            }
        }
        Err("Service not found".to_string())
    }
}
