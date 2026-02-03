import ray
import time
import asyncio
import uuid

# --- 模拟 RDMA 共享显存 ---
# 在真实的生产环境中，这里会是 Redis 或 etcd 存储 KV Cache 的 Metdata，
# 而实际的数据传输会走底层的高速 RDMA 网络。
KV_CACHE_REGISTRY = {} 

# --- Prefill Node ---
# 必须调度到 H100 上
@ray.remote(num_gpus=1, resources={"nvidia.com/gpu": 1}) 
class PrefillWorker:
    def __init__(self, worker_id):
        self.worker_id = worker_id
        print(f"🔥 [PrefillWorker-{worker_id}] Initialized on H100.")

    async def prefill(self, prompt: str):
        request_id = str(uuid.uuid4())[:8]
        print(f"🔥 [PrefillWorker-{self.worker_id}] Processing Req {request_id} (Prompt: {len(prompt)} chars)...")
        
        # 1. 计算 (Compute Bound)
        # 模拟 H100 的高速计算，很快算完
        await asyncio.sleep(0.5) 
        
        # 2. 生成 KV Cache
        # 假设生成了 500MB 数据
        kv_cache_data = f"KV_DATA_FOR_{request_id}_{'x'*100}" 
        
        # 3. 写入共享存储 (Simulate RDMA Write)
        # 真实的 RDMA 是直接写到目标机器内存，或者写到分布式存储
        KV_CACHE_REGISTRY[request_id] = kv_cache_data
        
        print(f"🔥 [PrefillWorker-{self.worker_id}] Handover: Cache {request_id} ready. (Size: 500MB)")
        return request_id, "First_Token"

# --- Decode Node ---
# 可以调度到 A10 上
@ray.remote(num_gpus=1, resources={"nvidia.com/gpu": 1})
class DecodeWorker:
    def __init__(self, worker_id):
        self.worker_id = worker_id
        print(f"🐢 [DecodeWorker-{worker_id}] Initialized on A10.")

    async def decode(self, request_id: str, max_tokens=10):
        print(f"🐢 [DecodeWorker-{self.worker_id}] Received handover for Req {request_id}")
        
        # 1. 读取 KV Cache (Simulate RDMA Read)
        # 模拟从远端拉取 500MB 数据的时间
        # 如果走 NVLink (机内) 只要 1ms
        # 如果走 RDMA (机间) 只要 5ms
        # 如果走 TCP (普通网) 可能要 500ms -> 这就是为什么要 RDMA
        start_transfer = time.time()
        kv_data = KV_CACHE_REGISTRY.get(request_id)
        if not kv_data:
            return "Error: KV Cache Miss!"
        
        # 模拟 RDMA 延迟
        await asyncio.sleep(0.005) 
        print(f"   --> KV Cache fetched via RDMA in {(time.time()-start_transfer)*1000:.2f}ms")
        
        # 2. 逐字生成 (Memory Bound)
        result = ""
        for i in range(max_tokens):
            await asyncio.sleep(0.1) # A10 比较慢
            token = f"tok{i} "
            result += token
            print(f"   ... Gen: {token}")
            
        print(f"🐢 [DecodeWorker-{self.worker_id}] Finished Req {request_id}")
        return result

# --- Driver (调度逻辑) ---
@ray.remote
def run_driver():
    # 启动 Worker
    p_worker = PrefillWorker.remote("P1")
    d_worker = DecodeWorker.remote("D1")
    
    # 模拟用户请求
    prompt = "Imagine a story about a brave knight..."
    
    # phase 1: Prefill
    # 这是一个 Python 的 await，但 Ray 会把这个任务打到 H100 节点去
    req_id, first_token = ray.get(p_worker.prefill.remote(prompt))
    print(f"\n✅ [Driver] Handover Triggered! ID: {req_id}, Token: {first_token}\n")
    
    # phase 2: Decode
    # 带着 ID 去找 Decode 节点
    final_output = ray.get(d_worker.decode.remote(req_id))
    print(f"\n🎉 [Result] {first_token} {final_output}")

if __name__ == "__main__":
    ray.init()
    ray.get(run_driver.remote())
