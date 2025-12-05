use anyhow::Result;
use reqwest::Client;
use std::sync::{Arc, Mutex};
use wasmtime::{Caller, Linker};

// 定义宿主状态 (Host State)，这是 Wasm 实例可以访问的外部上下文
// 例如：数据库连接池、HTTP 客户端、配置信息等
pub struct HostState {
    pub http_client: Client,
}

impl HostState {
    pub fn new() -> Self {
        Self {
            http_client: Client::new(),
        }
    }
}
