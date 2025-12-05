use std::thread;
use std::time::Duration;

fn main() {
    println!("Service started: Infinite Loop with Sleep");
    let mut count = 0;
    loop {
        println!("Service running... count: {}", count);
        count += 1;
        // Sleep for 1 second to avoid 100% CPU usage
        thread::sleep(Duration::from_secs(1));
    }
}
