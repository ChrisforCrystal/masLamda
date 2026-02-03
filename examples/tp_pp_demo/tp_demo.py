import os
import torch
import torch.distributed as dist
import torch.nn as nn

def setup(rank, world_size):
    # 配置 Master 节点地址/端口，用于多进程握手
    os.environ['MASTER_ADDR'] = 'localhost'
    os.environ['MASTER_PORT'] = '12355'
    # 初始化进程组，使用 'gloo' 后端 (兼容 CPU)
    dist.init_process_group("gloo", rank=rank, world_size=world_size)
    # 设置随机种子，确保所有进程的某些初始化行为一致 (在本例中其实主要是为了下面生成 full_weight)
    torch.manual_seed(42)  # Ensure deterministic init

def cleanup():
    # 销毁进程组，释放资源
    dist.destroy_process_group()

class ColumnParallelLinear(nn.Module):
    """
    列切分张量并行 (Column Parallel Linear Layer) 的简化实现
    
    数学原理: Y = X * W
    
    我们将权重矩阵 W 按列切分成两部分 [W1, W2]。
    - Rank 0 持有 W1
    - Rank 1 持有 W2
    
    计算过程:
    - Y1 = X * W1
    - Y2 = X * W2
    
    最终输出 Y = [Y1, Y2] (拼接起来)
    """
    def __init__(self, input_size, output_size, rank, world_size):
        super().__init__()
        self.rank = rank
        self.world_size = world_size
        
        # 确保输出维度能被进程数整除 (简化处理)
        assert output_size % world_size == 0
        self.partition_size = output_size // world_size
        
        # [演示用] 初始化完整的权重矩阵
        # 注意: 在真实的大模型训练中，我们根本无法在单卡内存中创建 full_weight，
        # 而是会直接在各卡上初始化属于自己的那一部分切片。
        full_weight = torch.randn(input_size, output_size)
        
        # 对权重进行切片 (Slice)
        # 假设 output_size=8, world_size=2
        # Rank 0 取列 [0:4], Rank 1 取列 [4:8]
        start_col = rank * self.partition_size
        end_col = (rank + 1) * self.partition_size
        
        # 将切片后的权重注册为参数
        self.weight = nn.Parameter(full_weight[:, start_col:end_col])
        print(f"✅ [Rank {rank}] 权重初始化完成: Shape={self.weight.shape} (只持有 1/{world_size})")

    def forward(self, x):
        # 1. 输入 X 分发给所有 Rank (这里假设每个 Rank 已经拿到了完整的副本 X)
        
        # 2. 本地计算 (Local Compute): Y_partial = X * W_partition
        # 结果的 Shape 是 (Batch, Output/N)
        y_partial = torch.matmul(x, self.weight)
        print(f"🔄 [Rank {self.rank}] 本地计算完成: Shape={y_partial.shape}")
        
        # 3. 集合通信 (All-Gather): 收集所有 Rank 的 partial result
        # 准备一个列表来存放收集到的结果
        gather_list = [torch.zeros_like(y_partial) for _ in range(self.world_size)]
        
        # 执行 All-Gather
        # Rank 0 会收到 [Rank0_Y, Rank1_Y]
        # Rank 1 也会收到 [Rank0_Y, Rank1_Y]
        dist.all_gather(gather_list, y_partial)
        
        # 4. 拼接 (Concatenate): 还原完整的输出 Y
        y_full = torch.cat(gather_list, dim=1)
        return y_full

def run_demo():
    # 从 torchrun 注入的环境变量中获取 Rank 信息
    rank = int(os.environ["RANK"])
    world_size = int(os.environ["WORLD_SIZE"])
    setup(rank, world_size)

    print(f"🚀 [Rank {rank}] 启动张量并行 (Tensor Parallelism) Demo...")

    # 定义模型维度
    BATCH_SIZE = 2
    INPUT_SIZE = 4
    OUTPUT_SIZE = 8  # 总输出维度为 8，将被切分到 2 个进程，每人负责 4
    
    # 创建并行层
    model = ColumnParallelLinear(INPUT_SIZE, OUTPUT_SIZE, rank, world_size)
    
    # 创建输入数据 (假设所有 Rank 的输入是一样的)
    input_data = torch.ones(BATCH_SIZE, INPUT_SIZE)
    
    # 前向传播
    output = model(input_data)
    
    if rank == 0:
        print("\n✨ [Rank 0] 最终输出已汇聚 (Gathered Y = [Y1, Y2]):")
        print(output)
        print(f"预期 Shape: ({BATCH_SIZE}, {OUTPUT_SIZE}) -> 实际: {output.shape}")
        
    cleanup()

if __name__ == "__main__":
    # 如果直接运行该脚本，提示用户使用 torchrun
    if "RANK" not in os.environ:
        print("请使用 torchrun 运行: torchrun --nproc_per_node=2 examples/tp_pp_demo/tp_demo.py")
    else:
        run_demo()
