"""
PD Separation 系统启动器

负责启动 Prefill 和 Decode 集群，并运行客户端测试
"""

import subprocess
import time
import sys
import os
import signal
import requests

PROCESSES = []

def start_process(cmd_list, log_prefix):
    print(f"🚀 启动 {log_prefix}...")
    log_file = open(f"{log_prefix.lower().replace(' ', '_')}.log", "w")
    p = subprocess.Popen(cmd_list, stdout=log_file, stderr=subprocess.STDOUT)
    PROCESSES.append(p)
    return p

def cleanup(sig=None, frame=None):
    print("\n🛑 停止所有进程...")
    for p in PROCESSES:
        p.terminate()
    print("✅ 所有进程已停止")
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)

def main():
    base_cmd = [sys.executable, "-m", "examples.pd_separation.engine"]
    
    print("=" * 60)
    print("   PD Separation 验证系统启动")
    print("=" * 60)
    
    # 1. 启动 Prefill 集群 (模拟 H100)
    print("\n[步骤 1/4] 启动 Prefill 集群...")
    start_process(base_cmd + [
        "--role", "PREFILL", "--rank", "0", "--world-size", "2", 
        "--master-port", "29500", "--port", "8000"
    ], "Prefill Leader")
    
    start_process(base_cmd + [
        "--role", "PREFILL", "--rank", "1", "--world-size", "2", 
        "--master-port", "29500"
    ], "Prefill Worker")
    
    # 2. 启动 Decode 集群 (模拟 A10)
    print("\n[步骤 2/4] 启动 Decode 集群...")
    start_process(base_cmd + [
        "--role", "DECODE", "--rank", "0", "--world-size", "2", 
        "--master-port", "29501", "--port", "8001"
    ], "Decode Leader")
    
    start_process(base_cmd + [
        "--role", "DECODE", "--rank", "1", "--world-size", "2", 
        "--master-port", "29501"
    ], "Decode Worker")

    print("\n[步骤 3/4] 等待集群初始化（5秒）...")
    time.sleep(5)
    
    # 3. 健康检查
    print("\n[步骤 4/4] 检查集群健康状态...")
    try:
        requests.get("http://localhost:8000/docs", timeout=1)
        requests.get("http://localhost:8001/docs", timeout=1)
        print("✅ Prefill 和 Decode 集群均已就绪!")
    except:
        print("❌ 集群启动失败，请检查日志文件")
        cleanup()
        return

    # 4. 运行客户端测试
    print("\n" + "=" * 60)
    print("   开始并发测试")
    print("=" * 60 + "\n")
    
    client_env = os.environ.copy()
    client_env["PREFILL_URL"] = "http://localhost:8000"
    client_env["DECODE_URL"] = "http://localhost:8001"
    
    subprocess.run([sys.executable, "-m", "examples.pd_separation.client"], env=client_env)
    
    # 结束
    print("\n" + "=" * 60)
    input("按 Enter 键停止所有服务...")
    cleanup()

if __name__ == "__main__":
    main()
