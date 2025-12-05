use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::io::{self, BufRead};

#[derive(Deserialize, Debug)]
pub struct RpcRequest {
    pub jsonrpc: String,
    pub id: String,
    pub method: String,
    pub params: Value,
}

#[derive(Serialize, Debug)]
pub struct RpcResponse {
    pub jsonrpc: String,
    pub id: String,
    pub result: Option<Value>,
    pub error: Option<RpcError>,
}

#[derive(Serialize, Debug)]
pub struct RpcError {
    pub code: i32,
    pub message: String,
}

pub type Handler = fn(Value) -> Result<Value, String>;

pub struct Service {
    handlers: HashMap<String, Handler>,
}

impl Service {
    pub fn new() -> Self {
        Self {
            handlers: HashMap::new(),
        }
    }

    pub fn register(&mut self, method: &str, handler: Handler) {
        self.handlers.insert(method.to_string(), handler);
    }

    pub fn run(&self) {
        eprintln!("DEBUG: Wasm Service Run Loop Started");
        let stdin = io::stdin();
        for line in stdin.lock().lines() {
            eprintln!("DEBUG: Waiting for input...");
            match line {
                Ok(input) => {
                    eprintln!("DEBUG: Received input: {}", input);
                    if let Ok(req) = serde_json::from_str::<RpcRequest>(&input) {
                        eprintln!("DEBUG: Parsed request: {:?}", req);
                        let response = if let Some(handler) = self.handlers.get(&req.method) {
                            match handler(req.params) {
                                Ok(result) => RpcResponse {
                                    jsonrpc: "2.0".to_string(),
                                    id: req.id,
                                    result: Some(result),
                                    error: None,
                                },
                                Err(msg) => RpcResponse {
                                    jsonrpc: "2.0".to_string(),
                                    id: req.id,
                                    result: None,
                                    error: Some(RpcError {
                                        code: -32603, // Internal error
                                        message: msg,
                                    }),
                                },
                            }
                        } else {
                            RpcResponse {
                                jsonrpc: "2.0".to_string(),
                                id: req.id,
                                result: None,
                                error: Some(RpcError {
                                    code: -32601, // Method not found
                                    message: format!("Method '{}' not found", req.method),
                                }),
                            }
                        };

                        if let Ok(json) = serde_json::to_string(&response) {
                            eprintln!("DEBUG: Sending response: {}", json);
                            println!("{}", json);
                            // Explicitly flush stdout
                            use std::io::Write;
                            let _ = io::stdout().flush();
                        }
                    } else {
                        // Ignore invalid JSON or non-RPC lines (could be logs?)
                        // For now, maybe just print them back or ignore?
                        // Spec says "Each request ... must be a valid JSON line"
                        // But we might want to log errors to stderr?
                        eprintln!("Invalid JSON-RPC request: {}", input);
                    }
                }
                Err(e) => {
                    eprintln!("DEBUG: Error reading line: {}", e);
                    break;
                }
            }
        }
        eprintln!("DEBUG: Wasm Service Run Loop Ended");
    }
}
