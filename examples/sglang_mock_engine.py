import asyncio
import time
import uuid
import json
import logging
from typing import List, Dict, Optional
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

# --- 日志配置 ---
# 设置日志级别为 INFO，格式包含时间戳、日志级别和消息内容
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sglang-mock")

# 初始化 FastAPI 应用
app = FastAPI(title="Mock SGLang Engine")

# --- Configuration (配置参数) ---
# 模拟每个 Token 生成的延迟时间 (0.1秒)，代表 GPU 推理速度
TOKEN_GENERATION_DELAY = 0.1  
# 默认生成的最大 Token 数
MAX_TOKENS = 20

# --- Radix Attention Simulation (核心：SGLang 前缀树缓存模拟) ---
# SGLang 的核心优势在于 RadixAttention，即通过前缀树 (Radix Trie) 来高效管理和复用 KV Cache。

class RadixNode:
    """ 
    前缀树节点类
    代表 Prompt 中的一个 Token 或 Token 序列
    """
    def __init__(self):
        self.children = {}  # 子节点字典：Map[token_string, RadixNode]
        self.count = 0      # 引用计数：记录有多少个请求复用了这个节点（用于缓存逐出策略 LRU/LFU）

class RadixCache:
    """
    RadixCache 类：模拟显存中的 KV Cache 存储结构
    
    原理：
    - 将所有历史请求的 Prompt 构建成一棵多叉树。
    - 当新请求到来时，在树中查找最长公共前缀 (Longest Common Prefix)。
    - 匹配到的部分不需要重新计算 (Prefill)，直接复用，从而极大降低首字延迟 (TTFT)。
    """
    def __init__(self):
        self.root = RadixNode() # 根节点，代表空前缀
        self.lock = asyncio.Lock() # 异步锁，保证并发安全性

    def match_prefix(self, tokens: List[str]) -> int:
        """
        核心算法：查找最长公共前缀
        Args:
            tokens: 当前请求分解后的 Token列表
        Returns:
            matched_len: 匹配到的长度 (即可以复用的 Token 数量)
        """
        node = self.root
        matched_len = 0
        for token in tokens:
            if token in node.children:
                node = node.children[token] # 继续向下匹配
                matched_len += 1
            else:
                break # 匹配中断
        return matched_len

    def insert(self, tokens: List[str]):
        """
        插入算法：将新的 Prompt 存入树中
        Args:
            tokens: 请求的 Token 列表
        作用：
            无论是否命中，请求结束后都将其路径更新到树中，
            为未来的请求提供复用机会（比如多轮对话的下一轮）。
        """
        node = self.root
        for token in tokens:
            if token not in node.children:
                node.children[token] = RadixNode() # 创建新节点
            node = node.children[token]
            node.count += 1 # 增加引用计数

# 全局单例 Cache 实例，模拟 GPU 显存
radix_cache = RadixCache()

# --- API 请求模型 ---
class ChatRequest(BaseModel):
    model: str # 模型名称
    messages: List[Dict[str, str]] # 对话历史：[{"role": "user", "content": "..."}]
    stream: bool = False # 是否开启流式输出
    max_tokens: Optional[int] = MAX_TOKENS # 最大生成长度

# --- 核心生成逻辑 ---
async def token_generator(request_id: str, prompt: str, max_tokens: int):
    """
    模拟 SGLang 的推理过程：Lookup -> Prefill -> Decode
    """
    # 0. Tokenization (简化版)
    # 实际会调用 HuggingFace Tokenizer，这里简单按空格切分
    tokens = prompt.split()
    
    # 1. Radix Attention Lookup (查找阶段)
    async with radix_cache.lock:
        # 问：这句话以前说过多少？
        hit_len = radix_cache.match_prefix(tokens)
        # 存：把这句话存进去供以后复用
        radix_cache.insert(tokens)
    
    total_len = len(tokens) # 总 Prompt 长度
    needed_len = total_len - hit_len # 需要计算的长度 = 总长度 - 命中长度
    
    # 计算并打印缓存命中率
    # Hit Ratio 高说明复用效果好，性能提升明显
    hit_ratio = (hit_len / total_len) * 100 if total_len > 0 else 0
    logger.info(f"🔍 [L-Cache] Req {request_id}: Len={total_len}, Hit={hit_len} ({hit_ratio:.1f}%)")

    # 2. Prefill (预填充/首字计算) 阶段
    # SGLang 核心优势：不需要为匹配到的部分 (hit_len) 重复计算 KV Cache。
    # 只需要计算剩下未匹配的部分 (needed_len)。
    # 模拟耗时：每个新 Token 需要 0.01秒
    prefill_time = needed_len * 0.01
    await asyncio.sleep(prefill_time)

    # 3. Decode (解码/生成) 阶段
    # 这一步是自回归生成，无法并行，只能一个一个字吐出来
    for i in range(max_tokens):
        # 模拟 GPU 计算延迟
        await asyncio.sleep(TOKEN_GENERATION_DELAY)
        
        token = f" tok_{i}" # 模拟生成的 Token 内容
        
        # 构造 OpenAI 兼容的 SSE 格式块
        chunk = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "mock-sglang",
            "choices": [{"delta": {"content": token}, "index": 0, "finish_reason": None}]
        }
        # yield 返回流式数据，格式严格遵循 SSE 规范 (data: ... \n\n)
        yield f"data: {json.dumps(chunk)}\n\n"
    
    # 4. 结束阶段
    # 发送 finish_reason='stop' 的块
    end_chunk = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": "mock-sglang",
        "choices": [{"delta": {}, "index": 0, "finish_reason": "stop"}]
    }
    yield f"data: {json.dumps(end_chunk)}\n\n"
    yield "data: [DONE]\n\n" # 标准结束标记
    
    logger.info(f"✅ [Finish] Req {request_id} Done.")


# --- API 路由 ---
@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    """
    OpenAI 兼容的 Chat Completions 接口
    """
    request_id = str(uuid.uuid4())[:8]
    # 提取最后一条用户消息作为 Prompt
    prompt = request.messages[-1]["content"] if request.messages else ""
    
    if request.stream:
        # 模式 A: 流式响应 (Streaming)
        # 返回 StreamingResponse，客户端会建立长连接接收 SSE 事件
        return StreamingResponse(
            token_generator(request_id, prompt, request.max_tokens or MAX_TOKENS),
            media_type="text/event-stream"
        )
    else:
        # 模式 B: 非流式响应 (Blocking)
        # 在服务端等待所有 Token 生成完毕，拼接成完整字符串后一次性返回
        full_response = ""
        async for chunk_str in token_generator(request_id, prompt, request.max_tokens or MAX_TOKENS):
             # 简单的 SSE 解析逻辑：提取 content 拼接到 full_response
             if "content" in chunk_str:
                import json
                try:
                    data = json.loads(chunk_str.replace("data: ", "").strip())
                    content = data["choices"][0]["delta"].get("content", "")
                    full_response += content
                except:
                    pass
        
        # 返回标准的完整 JSON 响应
        return {
            "id": request_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request.model,
            "choices": [{"message": {"role": "assistant", "content": full_response}, "finish_reason": "stop"}]
        }

if __name__ == "__main__":
    # 启动服务
    print(f"🔥 Mock SGLang Engine starting on http://0.0.0.0:8001")
    print(f"🧠 RadixAttention enabled.")
    uvicorn.run(app, host="0.0.0.0", port=8001)
