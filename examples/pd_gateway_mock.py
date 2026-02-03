import requests
import time

# ==========================================
# Gateway 逻辑示例 (The Waiter)
# 这是一个模拟的网关代码，负责调度 Prefill 和 Decode 两个独立的集群。
# ==========================================

# 真实场景下，这些 IP 是通过 K8s Service (DNS) 获取的
# 比如: http://prefill-pool-leader.inference-prod.svc:8000
PREFILL_URL = "http://localhost:8000" # 假设我们连的是 H100 集群
DECODE_URL  = "http://localhost:8001" # 假设我们连的是 A10 集群

def handle_user_request(prompt: str):
    print(f"🌍 [Gateway] Received User Request: '{prompt}'")
    
    # -------------------------------------------------
    # 步骤 1: 找 Prefill 集群 (切菜)
    # -------------------------------------------------
    print("➡️ [Gateway] Forwarding to Prefill Cluster (H100)...")
    try:
        # 这一步请求耗时较长，因为要处理从 Prompt 到 KV Cache 的转换
        resp = requests.post(f"{PREFILL_URL}/generate_prefill", params={"prompt": prompt})
        data = resp.json()
        
        kv_cache_id = data["kv_cache_id"]
        first_token = data["first_token"]
        print(f"⬅️ [Gateway] Prefill Done. ID: {kv_cache_id}, Tok1: {first_token}")
        
    except Exception as e:
        print(f"❌ Prefill Failed: {e}")
        return

    # -------------------------------------------------
    # 步骤 2: 找 Decode 集群 (炒菜)
    # -------------------------------------------------
    print(f"➡️ [Gateway] Forwarding to Decode Cluster (A10) with ID {kv_cache_id}...")
    try:
        # 把 Prefill 产生的令牌 (ID) 传给 Decode
        resp = requests.post(f"{DECODE_URL}/generate_decode", params={"kv_cache_id": kv_cache_id})
        result = resp.json()
        
        final_text = first_token + result["text"]
        print(f"✅ [Gateway] Response to User: {final_text}")
        
    except Exception as e:
        print(f"❌ Decode Failed: {e}")

if __name__ == "__main__":
    # 模拟用户请求
    handle_user_request("What is the capital of France?")
