import os
import torch
import torch.distributed as dist
import torch.nn as nn
import time
from datetime import datetime

def get_time():
    return datetime.now().strftime("%H:%M:%S")

def setup(rank, world_size):
    # 配置不同于 TP Demo 的端口，防止混淆
    os.environ['MASTER_ADDR'] = 'localhost'
    os.environ['MASTER_PORT'] = '12359' 
    dist.init_process_group("gloo", rank=rank, world_size=world_size)
    torch.manual_seed(42)

def cleanup():
    dist.destroy_process_group()

def simulate_compute(rank, stage_id, mb_id):
    """
    模拟计算耗时，专门为了可视化 '流水线气泡' (Pipeline Bubble)
    在真实场景中，这里的 sleep 对应的是 GPU 上的矩阵乘法时间
    """
    print(f"[{get_time()}] ⚙️  [Rank {rank}] Stage {stage_id} 开始计算 Micro-Batch {mb_id} ...")
    time.sleep(2.0) # 强制休眠 2秒，让等待现象更明显
    print(f"[{get_time()}] ✅ [Rank {rank}] Stage {stage_id} 完成计算 Micro-Batch {mb_id}")

def run_pp_bubble():
    """
    演示 Pipeline Parallelism 中的 '气泡' (Bubble) 现象
    
    架构: Rank 0 -> Rank 1 -> Rank 2 (3级流水线)
    流程: 
    1. Rank 0 产生数据，算完发给 Rank 1
    2. Rank 1 接收数据，算完发给 Rank 2
    3. Rank 2 接收数据，算完结束
    
    气泡 (Bubble): 指的是下游 Rank 在等待上游 Rank 计算结果时的空闲时间段。
    """
    rank = int(os.environ["RANK"])
    world_size = int(os.environ["WORLD_SIZE"])
    
    if world_size < 3:
        print("需要至少 3 个进程来演示 3级流水线! (请使用 --nproc_per_node=3)")
        return

    setup(rank, world_size)

    # 模拟 4 个 Micro-Batch 的连续请求
    # 如果没有流水线，总耗时 = 4 * (2s+2s+2s) = 24s
    # 有了流水线，大家可以同时干活
    NUM_MICRO_BATCHES = 4
    
    # === Logic for Rank 0 (Stage 1) ===
    if rank == 0:
        for i in range(NUM_MICRO_BATCHES):
            mb_id = i + 1
            # 1. Generate Data (模拟 DataLoader)
            data = torch.randn(2, 4)
            
            # 2. Compute (Stage 1 计算)
            simulate_compute(rank, 1, mb_id)
            
            # 3. Send to Next Stage (Rank 1)
            print(f"[{get_time()}] ➡️  [Rank 0] 发送 MB {mb_id} -> Rank 1")
            dist.send(data, dst=1)
            
        print(f"[{get_time()}] 🎉 [Rank 0] 所有任务已发出. 进入空闲状态 (Drain Phase/Bubble)...")
        # Rank 0 完成了它的所有工作，但它必须等待整个程序结束，这时候它的资源是浪费的

    # === Logic for Rank 1 (Stage 2) ===
    elif rank == 1:
        for i in range(NUM_MICRO_BATCHES):
            mb_id = i + 1
            # 1. Receive from Prev Stage
            buffer = torch.zeros(2, 4)
            # 【这里会产生气泡】如果 Rank 0 还没算完，Rank 1 只能干等
            print(f"[{get_time()}] ⏳ [Rank 1] 等待 MB {mb_id} (Bubble/Idle)...")
            dist.recv(buffer, src=0)
            
            # 2. Compute (Stage 2 计算)
            simulate_compute(rank, 2, mb_id)
            
            # 3. Send to Next Stage (Rank 2)
            print(f"[{get_time()}] ➡️  [Rank 1] 发送 MB {mb_id} -> Rank 2")
            dist.send(buffer, dst=2)

    # === Logic for Rank 2 (Stage 3) ===
    elif rank == 2:
        for i in range(NUM_MICRO_BATCHES):
            mb_id = i + 1
            # 1. Receive from Prev Stage
            buffer = torch.zeros(2, 4)
            # 【这里气泡最大】Rank 2 需要等 Rank 0 和 Rank 1 都跑起来后才能开始 (Fill Phase)
            print(f"[{get_time()}] ⏳ [Rank 2] 等待 MB {mb_id} (Bubble/Idle)...")
            dist.recv(buffer, src=1)
            
            # 2. Compute (Stage 3 计算)
            simulate_compute(rank, 3, mb_id)
            
            print(f"[{get_time()}] 🏁 [Rank 2] MB {mb_id} 最终完成!")

    cleanup()

if __name__ == "__main__":
    if "RANK" not in os.environ:
         print("请使用: torchrun --nproc_per_node=3 examples/tp_pp_demo/pp_bubble.py")
    else:
        run_pp_bubble()
