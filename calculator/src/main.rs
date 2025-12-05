mod wasm_rpc_helper;
use serde::Deserialize;
use serde_json::{json, Value};
use wasm_rpc_helper::Service;

#[derive(Deserialize)]
struct AddParams {
    a: i32,
    b: i32,
}

fn add(params: Value) -> Result<Value, String> {
    let p: AddParams = serde_json::from_value(params).map_err(|e| e.to_string())?;
    Ok(json!(p.a + p.b))
}

fn main() {
    eprintln!("DEBUG: Calculator Wasm Started (Stderr)");
    println!("DEBUG: Calculator Wasm Started (Stdout)");
    let mut service = Service::new();
    service.register("add", add);
    service.run();
}
