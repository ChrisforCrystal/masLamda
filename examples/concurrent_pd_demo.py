import requests
import threading
import time
import os
import traceback
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 模拟 5 个用户同时并发请求 (Concurrency Demo) - DEBUG MODE
# ==========================================

PROMPT = "I am reay a good man who realy love to study AI knownlede,..i am the ......"

# 使用环境变量配置 URL
PREFILL_URL = os.getenv("PREFILL_URL", "http://localhost:8000")
DECODE_URL = os.getenv("DECODE_URL", "http://localhost:8001")

def user_client(user_id):
    start_time = time.time()
    print(f"👤 [User-{user_id}] Sending Request...")
    
    try:
        # 1. Gateway 逻辑: Call Prefill
        url_p = f"{PREFILL_URL}/generate_prefill"
        resp_p = requests.post(url_p, params={"prompt": PROMPT}, timeout=10)
        
        if resp_p.status_code != 200:
            print(f"❌ [User-{user_id}] Prefill Status {resp_p.status_code}: {resp_p.text[:100]}")
            return

        try:
            data = resp_p.json()
        except Exception:
            print(f"❌ [User-{user_id}] INVALID JSON: {resp_p.text[:100]}")
            return

        # 详细打印 RESPONSE，看看到底有没有 kv_cache_id
        # print(f"DEBUG [User-{user_id}] Resp Data: {data}")

        if "kv_cache_id" not in data:
             print(f"❌ [User-{user_id}] Missing 'kv_cache_id' in: {data.keys()}")
             return
             
        kv_id = data["kv_cache_id"]
        
        # 2. Gateway 逻辑: Call Decode
        url_d = f"{DECODE_URL}/generate_decode"
        resp_d = requests.post(url_d, params={"kv_cache_id": kv_id}, timeout=10)
        
        if resp_d.status_code != 200:
            print(f"❌ [User-{user_id}] Decode Status {resp_d.status_code}: {resp_d.text[:100]}")
            return

        result = resp_d.json()
        if "text" not in result:
             print(f"❌ [User-{user_id}] Missing 'text' in Decode Resp: {result.keys()}")
             return

        total_time = time.time() - start_time
        print(f"✅ [User-{user_id}] Finished in {total_time:.2f}s. Result: ...{result['text']}")
        
    except Exception as e:
        print(f"❌ [User-{user_id}] Exception: {e}")
        # 打印这一行的堆栈，看看具体死在哪
        traceback.print_exc()

if __name__ == "__main__":
    t0 = time.time()
    # 模拟 5 个并发用户
    with ThreadPoolExecutor(max_workers=5) as executor:
        for i in range(5):
            executor.submit(user_client, i+1)
            
    print(f"\n⏱️ Total Wall Time for 5 Users: {time.time() - t0:.2f}s")
