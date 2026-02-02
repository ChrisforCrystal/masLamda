import asyncio
import time
import uuid
import random
import json
from typing import List, Dict, Optional
from typing import List, Dict, Optional
from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn
import logging

# --- 日志配置 ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vllm-mock")

app = FastAPI(title="Mock vLLM Engine")

# --- Configuration (配置参数) ---
# [PagedAttention 概念映射]
# TOTAL_GPU_SLOTS 模拟的是 GPU 中的 "Physical Blocks" 总数。
# - 原理: vLLM 不会一次性申请 80G 显存，而是把显存切成无数个 4KB 小块 (Block)。
# - 映射: 这里假设我们的 GPU 一共只有 10 个 Block (Total Physical Memory)。
TOTAL_GPU_SLOTS = 10  
TOKEN_GENERATION_DELAY = 0.1
MAX_TOKENS = 20

# --- State (全局调度状态) ---
class SchedulerState:
    """
    [Block Manager 模拟]
    在 vLLM C++ 代码中，这是由 BlockManager 负责的。
    它维护着一张巨大的映射表：Logical Block -> Physical Block。
    """
    def __init__(self):
        # running_slots: 代表当前已被分配出去的 "Physical Blocks" 数量
        self.running_slots = 0 
        self.waiting_queue = asyncio.Queue()
        self.lock = asyncio.Lock()

scheduler = SchedulerState()

class ChatRequest(BaseModel):
    model: str
    messages: List[Dict[str, str]]
    stream: bool = False
    max_tokens: Optional[int] = MAX_TOKENS

async def token_generator(request_id: str, prompt: str, max_tokens: int):
    """
    模拟一个请求在 "Continuous Batching (持续批处理)" 过山车上的完整旅程。
    """
    
    # --- 阶段 1：排队安检 (Waiting Queue) ---
    # 在真正上车前，先检查车上有没有空座位 (Physical Blocks)
    async with scheduler.lock:
        if scheduler.running_slots >= TOTAL_GPU_SLOTS:
            logger.info(f"🛑 [Queue] Request {request_id} queued (GPU Full: {scheduler.running_slots}/{TOTAL_GPU_SLOTS})")
    
    # [重点：这里就是"随时候补上车"的逻辑]
    # 无限循环 = 在车站排队死等
    while True:
        async with scheduler.lock:
            # 只要车上 (GPU) 有 1 个还是空的 (running_slots < 10)
            if scheduler.running_slots < TOTAL_GPU_SLOTS:
                # 马上抢座！
                scheduler.running_slots += 1 
                # 抢到了！上车！
                logger.info(f"🚀 [Start] Request {request_id} Joined Batch. (Slots: {scheduler.running_slots}/{TOTAL_GPU_SLOTS})")
                break # 跳出排队循环，进入下面的计算过程
        # 没抢到？等 0.1秒 再看一眼 (Poll)
        await asyncio.sleep(0.1)

    try:
        # --- 阶段 3：过山车运行中 (Decoding) ---
        # 注意：这里的 sleep 模拟的是每一轮 GPU 计算 (Verification Step)。
        # 在真实 vLLM 中，是一个全局的大循环不断在跑。
        # 你在这个循环里跑你的，别的请求在它的循环里跑它的。
        # 只要大家都在 yield，大家就在同一个 Batch 里。
        
        # Prefill...
        prefill_time = len(prompt) * 0.01
        await asyncio.sleep(prefill_time)

        # Decode Loop...
        for i in range(max_tokens):
            await asyncio.sleep(TOKEN_GENERATION_DELAY)
            
            token = f" tok_{i}"
            chunk = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "mock-gpt",
                "choices": [{"delta": {"content": token}, "index": 0, "finish_reason": None}]
            }
            yield f"data: {json.dumps(chunk)}\n\n"
        
        # Finish Chunk...
        end_chunk = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "mock-gpt",
            "choices": [{"delta": {}, "index": 0, "finish_reason": "stop"}]
        }
        yield f"data: {json.dumps(end_chunk)}\n\n"
        yield "data: [DONE]\n\n"

    finally:
        # --- 阶段 4：下车 (Finish / Free) ---
        # 你的请求结束了，马上把座位让出来！
        # 后面排队的请求 (Waiting Queue) 看到 running_slots 变少，马上就能抢到这个位置。
        # 这就是 "Continuous Batching"：永远不让座位空着。
        async with scheduler.lock:
            scheduler.running_slots -= 1
            logger.info(f"✅ [Finish] Request {request_id} Left Batch. (Slots: {scheduler.running_slots}/{TOTAL_GPU_SLOTS})")

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    request_id = str(uuid.uuid4())[:8]
    prompt = request.messages[-1]["content"] if request.messages else ""
    
    logger.info(f"📥 [Receive] Request {request_id} received. Prompt length: {len(prompt)}")

    if request.stream:
        return StreamingResponse(
            token_generator(request_id, prompt, request.max_tokens or MAX_TOKENS),
            media_type="text/event-stream"
        )
    else:
        # 非流式处理 (累积所有 Token)
        full_response = ""
        async for chunk_str in token_generator(request_id, prompt, request.max_tokens or MAX_TOKENS):
            # 简单解析 SSE 字符串
            if "content" in chunk_str:
                import json
                try:
                    data = json.loads(chunk_str.replace("data: ", "").strip())
                    content = data["choices"][0]["delta"].get("content", "")
                    full_response += content
                except:
                    pass
        
        return {
            "id": request_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request.model,
            "choices": [{"message": {"role": "assistant", "content": full_response}, "finish_reason": "stop"}]
        }

if __name__ == "__main__":
    print(f"🔥 Mock vLLM Engine starting on http://0.0.0.0:8000")
    print(f"⚙️  Configuration: {TOTAL_GPU_SLOTS} GPU Slots, {TOKEN_GENERATION_DELAY}s/token")
    uvicorn.run(app, host="0.0.0.0", port=8000)
