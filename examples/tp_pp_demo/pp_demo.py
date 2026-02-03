import os
import torch
import torch.distributed as dist
import torch.nn as nn
import time

def setup(rank, world_size):
    # 设置 Master 节点的地址和端口，用于节点间握手
    os.environ['MASTER_ADDR'] = 'localhost'
    os.environ['MASTER_PORT'] = '12356' # 注意：端口要和 TP Demo 区分开，避免冲突
    # 初始化进程组，使用 gloo 后端 (CPU 模式友好)
    dist.init_process_group("gloo", rank=rank, world_size=world_size)
    torch.manual_seed(42)

def cleanup():
    dist.destroy_process_group()

class SimpleLayer(nn.Module):
    def __init__(self, id):
        super().__init__()
        self.id = id
        self.linear = nn.Linear(4, 4)
    
    def forward(self, x):
        print(f"  [Layer {self.id}] Computing... (模拟计算)")
        return self.linear(x)

def run_pp_demo():
    # 环境变量由 torchrun 自动注入
    rank = int(os.environ["RANK"])
    world_size = int(os.environ["WORLD_SIZE"])
    setup(rank, world_size)

    print(f"🚀 [Rank {rank}] 启动流水线并行 (Pipeline Parallelism) Demo...")
    
    # === 模型切分策略 (Model Partitioning) ===
    # 假设一个 4 层模型: Layer 1 -> Layer 2 -> Layer 3 -> Layer 4
    # 切分方案:
    #   Stage 1 (Rank 0 负责): Layer 1, Layer 2
    #   Stage 2 (Rank 1 负责): Layer 3, Layer 4
    
    if rank == 0:
        # --- STAGE 1 (前半段) ---
        model = nn.Sequential(
            SimpleLayer(1),
            SimpleLayer(2)
        )
        
        # 1. 前向计算 (Forward Pass)
        input_data = torch.randn(2, 4) # Batch Size = 2
        print(f"Input Data: {input_data[0][:2]}...")
        
        output_stage1 = model(input_data)
        print(f"➡️ [Rank 0] Stage 1 完成. 正在将激活值 (Activation) 发送给 Rank 1...")
        
        # 2. 点对点通信 (P2P Send): 把中间结果发给下一个 Stage
        # 注意: 这是一个同步操作，会阻塞直到发送完成
        dist.send(tensor=output_stage1, dst=1)
        print(f"✅ [Rank 0] 发送成功.")
        
    elif rank == 1:
        # --- STAGE 2 (后半段) ---
        model = nn.Sequential(
            SimpleLayer(3),
            SimpleLayer(4)
        )
        
        # 1. 准备接收缓冲区 (Receive Buffer)
        # 必须预先知道发送过来的 Tensor 形状
        recv_buffer = torch.zeros(2, 4)
        print(f"⏳ [Rank 1] 等待接收 Rank 0 的激活值...")
        
        # 2. 点对点通信 (P2P Recv): 从上一个 Stage 接收数据
        dist.recv(tensor=recv_buffer, src=0)
        print(f"📥 [Rank 1] 收到激活值.")
        
        # 3. 前向计算 (Forward Pass)
        # 用接收到的数据继续跑剩下的层
        final_output = model(recv_buffer)
        print(f"✨ [Rank 1] Stage 2 完成. 最终输出:\n{final_output}")
        
    cleanup()

if __name__ == "__main__":
    if "RANK" not in os.environ:
        print("请使用 torchrun 运行: torchrun --nproc_per_node=2 examples/tp_pp_demo/pp_demo.py")
    else:
        run_pp_demo()
