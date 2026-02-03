import requests
import json

# ==========================================
# 真实用户视角 (End User Client)
# 
# 用户的感知:
# 1. 我只知道有一个 Gateway 地址 (本例中假设 Gateway 跑在 8080)
# 2. 我不知道后面有 H100 还是 A10，也不知道什么 Prefill/Decode
# 3. 我就像调用 OpenAI API 一样调用它
# ==========================================

GATEWAY_URL = "http://localhost:8080" # 这是我们 gateway/main.py 监听的端口

def chat_with_llm(prompt):
    print(f"👤 User: {prompt}")
    print("🤖 AI: ", end="", flush=True)
    
    # 构造请求 (假设 Gateway 兼容 OpenAI 格式)
    payload = {
        "model": "deepseek-v3",
        "messages": [{"role": "user", "content": prompt}],
        "stream": True # 流式很重要！
    }
    
    try:
        # 发送请求给 Gateway
        # 注意：这里我们连的是 Gateway，不是 Engine！
        # Gateway 内部会自动去做 P/D 分离的调度
        with requests.post(f"{GATEWAY_URL}/v1/chat/completions", json=payload, stream=True) as resp:
            if resp.status_code != 200:
                print(f"\n❌ Error: {resp.text}")
                return

            for line in resp.iter_lines():
                if line:
                    # 解析 SSE 格式 (data: {...})
                    decoded_line = line.decode("utf-8")
                    if decoded_line.startswith("data: "):
                        data_str = decoded_line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            token = data["choices"][0]["delta"].get("content", "")
                            print(token, end="", flush=True)
                        except:
                            pass
                            
        print("\n✅ (Conversation Finished)\n")
        
    except Exception as e:
        print(f"\n❌ Connection Failed: {e}")
        print("💡 Tip: Make sure 'uvicorn gateway.main:app' is running on port 8080")

if __name__ == "__main__":
    # 模拟真实对话
    chat_with_llm("Why is the sky blue?")
    chat_with_llm("Explain Quantum Physics in 5 words.")
