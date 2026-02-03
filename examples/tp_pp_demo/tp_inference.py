import os
import torch
import torch.distributed as dist
import torch.nn as nn
import sys

# === 组网配置 ===
# World Size = 3
# Rank 0: Master (Controller) - 只负责 I/O 和调度
# Rank 1, 2: Workers (Compute) - 负责跑 TP 模型

def setup(rank, world_size):
    os.environ['MASTER_ADDR'] = 'localhost'
    os.environ['MASTER_PORT'] = '12358' # 新端口
    
    # 1. 全局通信组 (Global Group): 用于 Master 给所有人发指令
    dist.init_process_group("gloo", rank=rank, world_size=world_size)
    torch.manual_seed(42)

def get_compute_group(rank):
    """
    创建一个只包含 Worker [1, 2] 的通信组，用于 TP 内部通信
    这样 Worker 互相 All-Gather 时，不会傻傻等 Rank 0
    """
    worker_ranks = [1, 2]
    # new_group 需要所有人(包括 Rank 0)都调用，但只有在 group 内的人才能用它通信
    group = dist.new_group(ranks=worker_ranks)
    return group, worker_ranks

class ColumnParallelLinear(nn.Module):
    def __init__(self, input_size, output_size, rank, tp_group):
        super().__init__()
        self.rank = rank
        self.tp_group = tp_group
        self.tp_world_size = dist.get_world_size(group=tp_group)
        
        # 这里的 rank 是全局 Rank (1 或 2)
        # 我们需要把它映射成组内 Rank (0 或 1) 来切分权重
        # 简单起见，我们用 (rank - 1)
        local_rank = rank - 1 
        
        assert output_size % self.tp_world_size == 0
        partition_size = output_size // self.tp_world_size
        
        # 初始化权重 (只切分不计算)
        full_weight = torch.randn(input_size, output_size)
        start_col = local_rank * partition_size
        end_col = (local_rank + 1) * partition_size
        
        self.weight = nn.Parameter(full_weight[:, start_col:end_col])
        print(f"  Example: [Rank {rank}] 权重加载完毕. Shape={self.weight.shape}")

    def forward(self, x):
        # 1. 本地计算
        y_partial = torch.matmul(x, self.weight)
        
        # 2. TP 组内聚合 (只在 Rank 1 和 2 之间发生)
        gather_list = [torch.zeros_like(y_partial) for _ in range(self.tp_world_size)]
        dist.all_gather(gather_list, y_partial, group=self.tp_group)
        
        return torch.cat(gather_list, dim=1)

def run_controller(rank):
    """Rank 0: 纯管理者"""
    print(f"👑 [Rank 0] Master 启动. 等待用户输入...")
    
    while True:
        input_tensor = torch.zeros(1, 4)
        should_exit = torch.zeros(1, dtype=torch.int)

        try:
            print("\n" + "="*40)
            user_text = input("👤 Master: 请输入 Prompt (输入 'exit' 退出): ")
            if user_text.strip().lower() == 'exit':
                should_exit[0] = 1
            else:
                # 模拟处理
                seed = len(user_text)
                torch.manual_seed(seed)
                input_tensor = torch.randn(1, 4)
        except EOFError:
            should_exit[0] = 1

        # 1. 广播指令 (给所有人)
        dist.broadcast(should_exit, src=0)
        if should_exit[0] == 1:
            print("👑 Master: 发送停机信号...")
            break
            
        # 2. 广播数据 (给所有人)
        print(f"📡 Master: 广播输入 -> Workers...")
        dist.broadcast(input_tensor, src=0)
        
        # 3. 等待 Worker 1 返回结果 (Point-to-Point)
        # 假设我们只从 Rank 1 收最终结果
        result_buffer = torch.zeros(1, 8) # Output dim is 8
        dist.recv(result_buffer, src=1)
        
        print(f"✅ Master: 收到计算结果: {result_buffer.data[0][:4]}...")

def run_worker(rank, tp_group):
    """Rank 1 & 2: 纯打工仔"""
    print(f"👷 [Rank {rank}] Worker 启动. 加入计算组.")
    
    # 初始化模型 (只存在于 Worker 内存中)
    model = ColumnParallelLinear(4, 8, rank, tp_group)
    
    while True:
        # 1. 等待指令
        should_exit = torch.zeros(1, dtype=torch.int)
        dist.broadcast(should_exit, src=0)
        if should_exit[0] == 1:
            print(f"👋 [Rank {rank}] Worker 下班.")
            break
            
        # 2. 等待数据
        input_tensor = torch.zeros(1, 4)
        dist.broadcast(input_tensor, src=0)
        
        # 3. TP 并行计算
        # 这一步包含内部的 All-Gather，会阻塞直到所有 Worker 都到齐
        output = model(input_tensor)
        print(f"  ⚡️ [Rank {rank}] 计算完成.")
        
        # 4. 上报结果
        # 只有 Rank 1 负责把结果发回给 Master
        if rank == 1:
            dist.send(output, dst=0)

def main():
    if "RANK" not in os.environ:
         print("请使用: torchrun --nproc_per_node=3 examples/tp_pp_demo/tp_inference.py")
         return

    rank = int(os.environ["RANK"])
    world_size = int(os.environ["WORLD_SIZE"])
    
    # 必须是 3 个进程
    if world_size < 3:
        print("需要至少 3 个进程 (1 Master + 2 Workers)")
        return

    setup(rank, world_size)
    
    # 创建计算组 (所有人都要调用，但只有 1,2 会在组里)
    tp_group, _ = get_compute_group(rank)

    if rank == 0:
        run_controller(rank)
    else:
        run_worker(rank, tp_group)
        
    cleanup()

def cleanup():
    dist.destroy_process_group()

if __name__ == "__main__":
    main()
