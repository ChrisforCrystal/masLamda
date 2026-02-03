import subprocess
import time
import sys
import os
import signal
import requests

# ==========================================
# 本地一键启动脚本 (End-to-End Runner)
# 职责:
# 1. 启动 2 个 Prefill 进程 (Leader Port 8000, Worker)
# 2. 启动 2 个 Decode 进程 (Leader Port 8001, Worker)
# 3. 运行 Concurrent Demo Client
# 4. 自动清理所有进程
# ==========================================

PROCESSES = []

def start_process(cmd_list, log_prefix):
    print(f"🚀 Launching {log_prefix}...")
    # [Debug Fix] 把日志输出到文件，而不是丢弃 (DEVNULL)，否则看不到报错
    log_file = open(f"{log_prefix.lower()}.log", "w")
    p = subprocess.Popen(cmd_list, stdout=log_file, stderr=subprocess.STDOUT)
    PROCESSES.append(p)
    return p

def cleanup(sig=None, frame=None):
    print("\n🛑 Stopping all clusters...")
    for p in PROCESSES:
        p.terminate()
    print("✅ All simulations stopped.")
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)

def main():
    base_cmd = [sys.executable, "examples/lws_inference_engine.py"]
    
    # 1. 启动 Prefill Cluster (H100)
    # Leader: Rank 0, HTTP 8000, Master 29500
    start_process(base_cmd + [
        "--role", "PREFILL", "--rank", "0", "--world-size", "2", 
        "--master-port", "29500", "--port", "8000"
    ], "Prefill-Leader")
    
    # Worker: Rank 1, Master 29500
    start_process(base_cmd + [
        "--role", "PREFILL", "--rank", "1", "--world-size", "2", 
        "--master-port", "29500"
    ], "Prefill-Worker")
    
    # 2. 启动 Decode Cluster (A10)
    # Leader: Rank 0, HTTP 8001, Master 29501
    start_process(base_cmd + [
        "--role", "DECODE", "--rank", "0", "--world-size", "2", 
        "--master-port", "29501", "--port", "8001"
    ], "Decode-Leader")
    
    # Worker: Rank 1, Master 29501
    start_process(base_cmd + [
        "--role", "DECODE", "--rank", "1", "--world-size", "2", 
        "--master-port", "29501"
    ], "Decode-Worker")

    print("\n⏳ Waiting 5s for clusters to initialize...")
    time.sleep(5)
    
    # 3. 检查健康状况
    try:
        requests.get("http://localhost:8000/docs", timeout=1)
        requests.get("http://localhost:8001/docs", timeout=1)
        print("✅ Both Clusters are ONLINE!")
    except:
        print("❌ Clusters failed to start. Check ports 8000/8001.")
        cleanup()

    # 4. 运行 Client Demo
    print("\n🎬 Running Concurrent Client Demo...")
    
    # 使用环境变量传递配置，不再修改文件
    client_env = os.environ.copy()
    client_env["PREFILL_URL"] = "http://localhost:8000"
    client_env["DECODE_URL"] = "http://localhost:8001"
    
    subprocess.run([sys.executable, "examples/concurrent_pd_demo.py"], env=client_env)
    
    # 结束
    input("\nPress Enter to stop...")
    cleanup()

if __name__ == "__main__":
    main()
