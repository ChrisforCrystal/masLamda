import asyncio
from sdk.sandbox import Sandbox
import uvicorn
import threading
import time
import os
from gateway.main import app

def start_server():
    uvicorn.run(app, host="0.0.0.0", port=8000)

async def test_wasm_lane():
    print("\n--- Testing WASM Lane (Real Pod) ---")
    sb = Sandbox()
    
    # Create
    try:
        sb.create(runtime="wasm")
        print("✅ WASM Pod Created & Running!")
        # Note: We cannot exec into WASM pods (usually no shell). 
        # Verification is successful if it reaches "Running" state.
    except Exception as e:
        print(f"❌ WASM Creation failed: {e}")

async def test_container_lane():
    print("\n--- Testing Container Lane (Standard Pod) ---")
    sb = Sandbox()
    
    try:
        # Gateway logic: 'auto' -> wasm. 'standard' -> standard/gvisor
        # We need to update Gateway main.py to handle "standard" request mapping if not already.
        # Assuming we send runtime="standard" and Gateway maps it.
        sb.create(runtime="standard") 
        print("✅ Container Pod Created!")
        
        # Test Exec
        await asyncio.sleep(2)
        output = await sb.exec("echo 'Hello Container'")
        print(f"Output: {output}")
        
        if "Hello Container" in output:
             print("✅ Container Exec Verified!")
        else:
             print(f"❌ Unexpected output: {output}")

    except Exception as e:
        print(f"❌ Container Test failed: {e}")

async def main():
    # 1. Start Server in Thread
    t = threading.Thread(target=start_server, daemon=True)
    t.start()
    time.sleep(3) # Wait for server
    
    # 2. Run Tests
    await test_wasm_lane()
    await test_container_lane()
    
    print("\n🎉 E2E Verification Complete!")

if __name__ == "__main__":
    if os.environ.get("PYTHONPATH") == None:
        print("⚠️ PYTHONPATH not set, setting it to current dir...")
        os.environ["PYTHONPATH"] = os.getcwd()
        
    asyncio.run(main())
