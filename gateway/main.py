from fastapi import FastAPI, WebSocket, HTTPException
import uuid
import asyncio
import json
from .backends.k8s_backend import K8SBackend

app = FastAPI()
# 初始化 Kubernetes 后端，用于和 K8s API Server 交互
k8s = K8SBackend()

# 简单的内存会话存储
# 生产环境通常会使用 Redis 或数据库来存储 SandboxID 到 Pod 的映射关系
sandboxes = {}

class SandboxSession:
    """定义沙箱会话对象"""
    def __init__(self, id, pod_name, runtime):
        self.id = id              # 沙箱唯一ID
        self.pod_name = pod_name  # 对应的 K8s Pod 名称
        self.runtime = runtime    # 使用的运行时类型 (wasm/gvisor/standard)

from pydantic import BaseModel

class CreateSandboxRequest(BaseModel):
    runtime: str = "auto" # 客户端请求的运行时类型，默认为自动选择

# [API] 创建沙箱
# 负责接收用户请求，选择合适的 Runtime，并在 K8s 中启动 Pod
@app.post("/sandboxes")
async def create_sandbox(req: CreateSandboxRequest):
    runtime = req.runtime
    # 生成一个简短的唯一 ID，作为沙箱标识
    sb_id = f"sb-{uuid.uuid4().hex[:6]}"
    
    # [核心逻辑] 路由策略：根据请求类型选择 K8s RuntimeClass
    # 这一步是 Gateway 的核心，屏蔽了底层的异构计算资源
    k8s_runtime = None
    if runtime == "kata":
        # Kata Containers with QEMU (Recommended for compatibility)
        k8s_runtime = "kata-qemu"
        image = "image.midea.com/midea-middleware/python:3.13.7-slim-bookworm"
    elif runtime == "wasm":
        # 如果请求 Wasm，映射到集群里的 KWasm RuntimeClass
        k8s_runtime = "wasm-edge-v1" 
        # Wasm 通常需要特殊的镜像 (编译为 .wasm 文件的容器)
        image = "wasmedge/example-wasi-http:latest" 
    elif runtime == "gvisor":
        # 如果请求强隔离，映射到 gVisor RuntimeClass
        k8s_runtime = "gvisor" 
        # gVisor 可以运行普通的 OCI 镜像 (如 Python, Node等)
        image = "image.midea.com/midea-middleware/python:3.13.7-slim-bookworm" 
    else:
        # "standard" 或 "auto" 或其他情况 -> 默认回退到标准 runc (普通容器)
        k8s_runtime = None 
        image = "image.midea.com/midea-middleware/python:3.13.7-slim-bookworm" 

    print(f"Creating Sandbox {sb_id} with RuntimeClass: {k8s_runtime}")
    
    # 调用 K8s 后端创建 Pod
    try:
        pod_name = await k8s.create_pod(sb_id, image, k8s_runtime)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # 保存会话信息到内存，供后续 WebSocket 连接使用
    sandboxes[sb_id] = SandboxSession(sb_id, pod_name, runtime)
    
    # 返回连接信息给客户端
    return {
        "id": sb_id,
        "runtime": k8s_runtime or "standard",
        "ws_url": f"/connect/{sb_id}" # 客户端拿着这个 URL 来建立 WebSocket
    }

# [API] WebSocket 连接
# 建立长连接，实现与沙箱内进程的实时交互 (Exec)
@app.websocket("/connect/{sb_id}")
async def websocket_endpoint(websocket: WebSocket, sb_id: str):
    await websocket.accept()
    
    # 查找沙箱会话
    sb = sandboxes.get(sb_id)
    if not sb:
        await websocket.close(code=4004, reason="Sandbox not found")
        return

    try:
        while True:
            # 接收客户端发来的指令
            data = await websocket.receive_text()
            req = json.loads(data)
            
            if req.get("type") == "exec":
                cmd = req.get("cmd")
                # [核心逻辑] 远程执行
                # 调用 K8s exec 接口在 Pod 内执行命令
                try:
                    output = await k8s.exec_command(sb.pod_name, cmd)
                    # 将执行结果回传给客户端
                    await websocket.send_text(json.dumps({
                        "type": "stdout",
                        "data": output
                    }))
                except Exception as e:
                    await websocket.send_text(json.dumps({
                        "type": "stderr",
                        "data": str(e)
                    }))
                
    except Exception as e:
        print(f"WS Error: {e}")
