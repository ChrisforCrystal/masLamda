#!/usr/bin/env python3
"""
简化的沙箱演示脚本 - 仅测试 runc 和 Kata QEMU

这个脚本演示了如何通过 Gateway API 创建两种不同运行时的沙箱：
1. **Standard (runc)**: 传统容器运行时
2. **Kata Containers (QEMU)**: 虚拟机级别隔离的沙箱

适用于远程集群环境，不需要安装 gVisor 或 Wasm。
"""

import requests
import websocket
import json
import time
import sys

# Gateway API 地址
GATEWAY_URL = "http://localhost:8000"

def test_sandbox(runtime: str):
    """测试指定运行时的沙箱创建和命令执行"""
    print(f"\n{'='*60}")
    print(f"🚀 测试 Runtime: {runtime.upper()}")
    print(f"{'='*60}")
    
    # 1. 创建沙箱
    print(f"\n[步骤 1] 正在创建 {runtime} 沙箱...")
    try:
        resp = requests.post(f"{GATEWAY_URL}/sandboxes", json={
            "runtime": runtime
        })
        resp.raise_for_status()
        sandbox = resp.json()
        print(f"✅ 沙箱创建成功!")
        print(f"   ID: {sandbox['id']}")
        print(f"   Runtime: {sandbox['runtime']}")
        print(f"   WebSocket URL: {sandbox['ws_url']}")
    except Exception as e:
        print(f"❌ 创建沙箱失败: {e}")
        return False
    
    # 等待 Pod 启动
    print(f"\n[步骤 2] 等待沙箱就绪...")
    time.sleep(8 if runtime == "kata" else 5)  # Kata 启动稍慢，多等几秒
    
    # 2. 连接 WebSocket 并执行命令
    print(f"\n[步骤 3] 连接 WebSocket 并执行命令...")
    ws_url = f"ws://localhost:8000{sandbox['ws_url']}"
    
    try:
        ws = websocket.create_connection(ws_url)
        print(f"✅ WebSocket 连接成功!")
        
        # 测试命令列表
        commands = [
            "uname -a",           # 查看内核信息（Kata 会显示虚拟机内核）
            "cat /proc/cpuinfo | grep 'model name' | head -1",  # CPU 信息
            "python3 --version",  # Python 版本
            # 执行一段实际的 Python 代码 (计算 100万 以内的累加和)
            """python3 -c "import time; start=time.time(); print(f'Sum(1M)={sum(range(1000000))} (Time: {time.time()-start:.4f}s)')" """,
        ]
        
        for cmd in commands:
            print(f"\n  💻 执行命令: {cmd}")
            ws.send(json.dumps({"type": "exec", "cmd": cmd}))
            result = ws.recv()
            data = json.loads(result)
            
            if data["type"] == "stdout":
                # 输出格式化
                output = data["data"].strip()
                for line in output.split('\n'):
                    print(f"     {line}")
            else:
                print(f"     ❌ 错误: {data['data']}")
        
        ws.close()
        print(f"\n✅ {runtime.upper()} 运行时测试完成!")
        return True
        
    except Exception as e:
        print(f"❌ WebSocket 执行失败: {e}")
        return False

def main():
    print("="*60)
    print("  MasLambda 简化沙箱演示 - Runc vs Kata QEMU")
    print("="*60)
    print("\n这个演示将对比两种运行时：")
    print("  1. Standard (runc)    - 传统容器隔离")
    print("  2. Kata (QEMU) - 虚拟机级别隔离\n")
    
    # 测试 Standard Runtime
    success_standard = test_sandbox("standard")
    
    # 稍作间隔
    time.sleep(2)
    
    # 测试 Kata Runtime
    success_kata = test_sandbox("kata")
    
    # 总结
    print(f"\n{'='*60}")
    print("📊 测试结果总结")
    print(f"{'='*60}")
    print(f"  Standard (runc):    {'✅ 通过' if success_standard else '❌ 失败'}")
    print(f"  Kata (QEMU): {'✅ 通过' if success_kata else '❌ 失败'}")
    print(f"{'='*60}\n")
    
    if success_standard and success_kata:
        print("🎉 所有测试通过！您的 MasLambda 已成功支持多运行时沙箱!")
        return 0
    else:
        print("⚠️  部分测试失败，请检查日志排查问题。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
