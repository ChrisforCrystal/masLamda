import requests
import json
import websockets
import asyncio

class Sandbox:
    """
    Unified Sandbox SDK
    为 Agent 提供统一的接口来管理和使用不同类型的沙箱环境。
    屏蔽了底层的 REST API 和 WebSocket 通信细节。
    """
    def __init__(self, gateway_url="http://localhost:8000"):
        self.gateway_url = gateway_url # Gateway 服务地址
        self.ws_url = None             # WebSocket 连接地址 (创建沙箱后获取)
        self.id = None                 # 沙箱会话 ID
        self.ws = None                 # WebSocket 连接对象

    def create(self, runtime="auto"):
        """
        [1. 创建资源]
        调用 Gateway REST API 申请一个新的沙箱实例。
        :param runtime: "auto" | "wasm" | "gvisor" | "standard"
        """
        res = requests.post(f"{self.gateway_url}/sandboxes", json={"runtime": runtime})
        if res.status_code != 200:
            raise Exception(f"Failed to create sandbox: {res.text}")
        
        data = res.json()
        self.id = data["id"]
        # 构造 WebSocket URL (真实场景下应该是 wss:// 且通过 Gateway 发现服务返回完整地址)
        self.ws_url = f"ws://localhost:8000{data['ws_url']}"
        print(f"✅ Sandbox Created: {self.id} (Runtime: {data['runtime']})")
        return self

    async def connect(self):
        """
        [2. 建立连接]
        初始化 WebSocket 长连接，准备进行指令交互。
        通常在 exec 之前自动调用，无需用户手动触发。
        """
        self.ws = await websockets.connect(self.ws_url)
        print("🔌 Connected to Sandbox Gateway")

    async def exec(self, cmd):
        """
        [3. 执行指令]
        通过 WebSocket 发送 Shell 命令并等待返回结果。
        :param cmd: 要执行的 Shell 命令字符串
        :return: 命令的标准输出 (stdout)
        """
        if not self.ws:
            await self.connect()
        
        req = {
            "type": "exec", # 消息类型
            "cmd": cmd      # 具体命令
        }
        await self.ws.send(json.dumps(req))
        
        # [等待响应] (MVP 简化版)
        # 实际生产中这里应该是异步流式处理，支持实时回显
        while True:
            resp = await self.ws.recv()
            msg = json.loads(resp)
            if msg["type"] == "stdout":
                return msg["data"]
            # TODO: Handle other types (stderr, exit_code)

    def close(self):
        # 资源清理 hook
        pass
