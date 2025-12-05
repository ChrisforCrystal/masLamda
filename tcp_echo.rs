use std::io::{Read, Write};
use std::net::TcpListener;

fn main() {
    println!("Starting TCP Echo Server on port 8080...");
    let listener = TcpListener::bind("0.0.0.0:8080").expect("Failed to bind to port 8080");

    for stream in listener.incoming() {
        match stream {
            Ok(mut stream) => {
                println!("New connection!");
                let mut buffer = [0; 1024];
                match stream.read(&mut buffer) {
                    Ok(n) => {
                        let received = String::from_utf8_lossy(&buffer[..n]);
                        println!("Received: {}", received);

                        let response = format!("Echo from Wasm: {}", received);
                        stream.write_all(response.as_bytes()).unwrap();
                    }
                    Err(e) => println!("Failed to read: {}", e),
                }
            }
            Err(e) => println!("Connection failed: {}", e),
        }
    }
}
