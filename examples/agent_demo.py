import asyncio
import os
import sys

# [系统路径设置]
# 将项目根目录添加到 python path，确保可以正确导入 sdk 包
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sdk.sandbox import Sandbox

async def run_agent_task():
    print("🤖 [Agent] Initialization...")
    sb = Sandbox() 
    
    # ---------------------------------------------------------
    # 1. 实验 A：Standard Runtime (Runc - Shared Kernel)
    # 目标：展示"一长串文本"，证明它是一个完整的 Linux 环境
    # ---------------------------------------------------------
    print("\n📦 [Experiment A] Starting Standard Sandbox (Runc)...")
    try:
        sb_std = Sandbox().create(runtime="standard")
        print(f"✅ Sandbox Created: {sb_std.id}")
        
        # 用户要求：runc也能跑python代码。目标：与 gVisor 形成直接对比。
        # 我们执行一段 Python 代码，打印版本和平台信息，并进行数学计算
        py_code = "import sys, os; print(f'Hello from Standard Runc! Python {sys.version.split()[0]}'); print(f'Running on: {sys.platform}'); print(f'Math Test: 2^100 = {2**100}')"
        cmd = f"python -c \"{py_code}\""
        
        print(f"🚀 Executing Python: {py_code}")
        output = await sb_std.exec(cmd)
        print(f"📺 [Standard Output (Python Runtime)]:\n{output.strip()}")
        
    except Exception as e:
        print(f"❌ Standard Sandbox Failed: {e}")

    # ---------------------------------------------------------
    # 2. 实验 B：gVisor Runtime (Runsc - Secure Python)
    # 目标：执行一段 Python 代码，证明它支持通用语言但内核是隔离的
    # ---------------------------------------------------------
    print("\n🛡️ [Experiment B] Starting gVisor Sandbox (Runsc)...")
    try:
        sb_gvisor = Sandbox().create(runtime="gvisor")
        print(f"✅ Sandbox Created: {sb_gvisor.id}")
        
        # 用户要求：gvisor一段python
        # 我们计算 2的100次方，并打印环境信息
        py_code = "import sys; print(f'Hello from gVisor! Python {sys.version.split()[0]}'); print(f'Math Test: 2^100 = {2**100}')"
        cmd = f"python -c \"{py_code}\""
        
        print(f"🚀 Executing Python: {py_code}")
        output = await sb_gvisor.exec(cmd)
        print(f"📺 [gVisor Output]:\n{output.strip()}")
        
    except Exception as e:
        print(f"❌ gVisor Sandbox Failed: {e}")

    # ---------------------------------------------------------
    # 3. 实验 C：Wasm Runtime (WasmEdge - High Performance Microservice)
    # 目标：Wasm 最适合做无服务器函数/微服务。我们直接访问它的 HTTP 接口。
    # ---------------------------------------------------------
    print("\n⚡ [Experiment C] Starting Wasm Sandbox (KWasm/WasmEdge)...")
    try:
        # Wasm 启动通常极快
        sb_wasm = Sandbox().create(runtime="wasm")
        print(f"✅ Sandbox Created: {sb_wasm.id}")
        
        # [Wasm 特有验证]：Port Forward & Curl
        # 因为 Wasm 容器没有 Shell，我们通过网络访问它来验证
        import subprocess
        import time
        import requests
        
        pod_name = f"sb-{sb_wasm.id}"
        local_port = 18080
        local_host = "127.0.0.1" # Force IPv4 to avoid localhost resolution issues
        
        print(f"🔌 [Client] Starting Port-Forward to {pod_name}:8080 -> {local_host}:{local_port}...")
        # 后台启动 port-forward
        pf_process = subprocess.Popen(
            ["kubectl", "port-forward", f"pod/{pod_name}", f"{local_port}:8080"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        try:
            # 等待连接建立 (Wasm 启动很快，但 port-forward 需要时间)
            print("⏳ Waiting for connection...")
            time.sleep(5)
            
            # 发送请求 (wasmedge/example-wasi-http 通常处理 /echo 或 /)
            # 我们尝试 POST /echo，并强制关闭连接 (Simple WASI servers often don't support Keep-Alive)
            url = f"http://{local_host}:{local_port}/echo"
            print(f"🚀 [Client] Sending HTTP Request to Wasm Service: POST {url}")
            
            headers = {"Connection": "close"}
            resp = requests.post(url, data="Hello Wasm from Client!", headers=headers)
            
            if resp.status_code == 200:
                print(f"📺 [Wasm Response]: {resp.text}")
                print("✅ Wasm Microservice is Working! (Served via Hyper-lightweight Runtime)")
            else:
                print(f"⚠️ Wasm responded with {resp.status_code}. Trying root path...")
                # Fallback to root
                resp = requests.get(f"http://{local_host}:{local_port}/", headers=headers)
                print(f"📺 [Wasm Root Response]: {resp.status_code}")
                if resp.status_code == 200:
                     print(f"📺 [Body]: {resp.text}")

        except Exception as e:
            print(f"❌ HTTP Test Failed: {e}")
        finally:
             # Just in case, print logs to confirm the server received something
            print("🔍 [System Check] Wasm Pod Logs (Proof of Liveness):")
            subprocess.run(["kubectl", "logs", pod_name], check=False)
            
            # 清理端口转发
            pf_process.terminate()
            print("🔌 [Client] Connection Closed.")
        
    except Exception as e:
        print(f"❌ Wasm Sandbox Failed: {e}")

    print("\n✨ [Agent] Comparison Complete!")

if __name__ == "__main__":
    asyncio.run(run_agent_task())
