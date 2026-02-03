import os
import torch
import torch.distributed as dist
import argparse
from fastapi import FastAPI
import uvicorn
import threading
import asyncio
import uuid
import time
from typing import List, Dict

# ==========================================
# LWS 高并发业务代码示例 (High Concurrency / Batching)
#
# [核心架构升级]:
# 1. 不再是一个请求占用一个锁 (Serialization)。
# 2. 引入 "Scheduler Loop" (调度器循环)。
# 3. HTTP 请求只负责把任务扔进队列 (Non-blocking)。
# 4. 调度器每隔 10ms 捞一批任务 (Batching)，一次广播发给 Worker。
# ==========================================

app = FastAPI()
MOCK_RDMA_STORE = {}

# 模拟配置
MAX_BATCH_SIZE = 8       # 一次最多处理 8 个
SCHEDULER_INTERVAL = 0.01 # 10ms 调度一次

# 任务队列 (Producer-Consumer)
# queue item: (request_id, prompt/kv_id, future)
PREFILL_QUEUE = asyncio.Queue()
DECODE_QUEUE = asyncio.Queue()

# 全局锁 (保护 NCCL，虽然是 Batch 操作，但发的时候还是要互斥)
DIST_LOCK = threading.Lock()

def init_distributed():
    role = os.getenv("INSTANCE_ROLE", "Unified") 
    master_addr = os.getenv("MASTER_ADDR", "localhost")
    world_size = int(os.getenv("WORLD_SIZE", "1"))
    rank = int(os.getenv("RANK", "0"))

    print(f"🚀 [{role} Role] Rank {rank}/{world_size} initialized. Leader: {master_addr}")
    dist.init_process_group("nccl", init_method=f"tcp://{master_addr}:29500", world_size=world_size, rank=rank)
    return rank, role

# --- 调度器核心 (The Engine Heartbeat) ---
async def scheduler_loop():
    print("💓 Scheduler Loop Started. Ready to batch requests...")
    while True:
        # 1. 尝试从队列捞一批 Prefill 任务
        batch_prefill = []
        while not PREFILL_QUEUE.empty() and len(batch_prefill) < MAX_BATCH_SIZE:
            batch_prefill.append(PREFILL_QUEUE.get_nowait())
            
        if batch_prefill:
            await process_batch("PREFILL", batch_prefill)

        # 2. 尝试从队列捞一批 Decode 任务
        batch_decode = []
        while not DECODE_QUEUE.empty() and len(batch_decode) < MAX_BATCH_SIZE:
            batch_decode.append(DECODE_QUEUE.get_nowait())
            
        if batch_decode:
            await process_batch("DECODE", batch_decode)

        # 休息一下，避免空转烧 CPU
        if not batch_prefill and not batch_decode:
            await asyncio.sleep(SCHEDULER_INTERVAL)

async def process_batch(req_type, batch_items):
    # batch_items 是 [(req_id, input_data, future)...] 的列表
    inputs = [item[1] for item in batch_items]
    ids = [item[0] for item in batch_items]
    
    print(f"⚡️ [Scheduler] Executing Batch {req_type} Size={len(inputs)}: {ids}")
    
    # [关键点] 在锁还没释放的时候，就把整个 Batch 广播出去了
    # 这就是并发的奥义：一次通信，处理 N 个请求
    with DIST_LOCK:
        cmds = [req_type, inputs] # inputs 是一个列表
        # 注意：这里需要在线程池里跑，防止阻塞 asyncio loop
        await asyncio.to_thread(dist_broadcast, cmds)
    
    # 模拟计算耗时 (Batch 越大，耗时稍微越长，但平均下来每个人更快)
    await asyncio.sleep(0.1 + 0.01 * len(inputs))
    
    # 唤醒所有等待的 HTTP 请求
    for i, (req_id, data, future) in enumerate(batch_items):
        if req_type == "PREFILL":
            # 写入 Mock RDMA
            kv_id = f"kv_{hash(data)}"
            MOCK_RDMA_STORE[kv_id] = "TensorData"
            future.set_result({"kv_cache_id": kv_id, "first_token": "Hi"})
        else:
            future.set_result({"text": f" batch-{i} done"})

def dist_broadcast(cmds):
    dist.broadcast_object_list(cmds, src=0)

# --- HTTP 接口 (这次是非阻塞的) ---

@app.post("/generate_prefill")
async def prefill(prompt: str):
    # 1. 生成排队号
    req_id = str(uuid.uuid4())[:8]
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    
    # 2. 扔进队列 (立马返回，不等待计算)
    await PREFILL_QUEUE.put((req_id, prompt, future))
    print(f"📥 [Gateway] Enqueued Prefill Req {req_id}")
    
    # 3. 挂起等待 (Await Future)
    # 这一步会让出控制权，去处理下一个 HTTP 请求
    result = await future
    return result

@app.post("/generate_decode")
async def decode(kv_cache_id: str):
    req_id = str(uuid.uuid4())[:8]
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    
    await DECODE_QUEUE.put((req_id, kv_cache_id, future))
    print(f"📥 [Gateway] Enqueued Decode Req {req_id}")
    
    result = await future
    return result

# --- Worker Loop (Batch Aware) ---
def run_worker_loop(role):
    # 单独起个 Event Loop 不需要，Worker 是同步的
    while True:
        cmds = [None, None]
        dist.broadcast_object_list(cmds, src=0)
        op_type, batch_data = cmds
        
        # Worker 拿收到的是一个列表 (Batch)
        batch_size = len(batch_data)
        
        if op_type == "PREFILL":
            print(f"🔥 [Worker-{role}] Batch Prefill: Processing {batch_size} prompts simultaneously!")
            # 真实场景 (Real vLLM):
            # ---------------------------------------------------
            # from vllm.engine.arg_utils import EngineArgs
            # from vllm.engine.async_llm_engine import AsyncLLMEngine
            #
            # # 1. 初始化引擎 (对接 H100/A10)
            # engine_args = EngineArgs(model="deepseek/deepseek-v3", tensor_parallel_size=world_size)
            # engine = AsyncLLMEngine.from_engine_args(engine_args)
            #
            # # 2. 真正计算
            # # vLLM 会自动处理 Batching, PagedAttention, 和 NCCL 通信
            # results = await engine.generate(batch_data.prompt, sampling_params)
            # ---------------------------------------------------
            
        elif op_type == "DECODE":
            print(f"🐢 [Worker-{role}] Batch Decode: Processing {batch_size} tokens simultaneously!")

# --- CLI Argument Parsing ---
def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", type=str, default="Combined", choices=["PREFILL", "DECODE", "Combined"])
    parser.add_argument("--rank", type=int, default=0)
    parser.add_argument("--world-size", type=int, default=1)
    parser.add_argument("--master-addr", type=str, default="localhost")
    parser.add_argument("--master-port", type=str, default="29500")
    parser.add_argument("--port", type=int, default=8000, help="HTTP Port for Leader")
    return parser.parse_args()

def init_distributed(args):
    # 使用 CLI 参数覆盖环境变量
    print(f"🚀 [{args.role} Role] Rank {args.rank}/{args.world_size} initialized. Master: {args.master_addr}:{args.master_port}")
    
    # [Local Test Trick] Use 'gloo' for CPU-only testing on Mac
    backend = "gloo" 
    
    dist.init_process_group(
        backend=backend, 
        init_method=f"tcp://{args.master_addr}:{args.master_port}", 
        world_size=args.world_size, 
        rank=args.rank
    )
    return args.rank, args.role

if __name__ == "__main__":
    args = parse_args()
    
    # 设置 Mock 存储的唯一标识（仅用于本地单进程模拟，多进程需用 Redis）
    # 但为了演示简单，我们假设各进程内存不共享，仅仅演示通信流程
    
    rank, role = init_distributed(args)
    
    if rank == 0:
        print(f"👑 I am the {role} LEADER. Starting Scheduler & HTTP on port {args.port}...")
        
        loop = asyncio.new_event_loop()
        config = uvicorn.Config(app, host="0.0.0.0", port=args.port, loop="asyncio")
        server = uvicorn.Server(config)
        
        async def main_loop():
            # 只有 Leader 需要跑调度循环
            asyncio.create_task(scheduler_loop())
            await server.serve()
            
        asyncio.run(main_loop())
        
    else:
        print(f"🔧 I am a {role} WORKER. Watching for Batches...")
        run_worker_loop(role)
