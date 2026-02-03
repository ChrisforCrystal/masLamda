import time
import argparse
import sys
import logging
import random

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [Rank %(process)d] %(message)s")
logger = logging.getLogger("fsdp-sim")

class MockGPU:
    """模拟一块 GPU 的显存行为"""
    def __init__(self, rank, vram_limit_gb=16.0):
        self.rank = rank
        self.vram_limit = vram_limit_gb * 1024 * 1024 * 1024  # Bytes
        self.used_vram = 0
        self.peak_vram = 0

    def allocate(self, size_bytes, name="Tensor"):
        """模拟显存申请 (malloc)"""
        required = size_bytes
        available = self.vram_limit - self.used_vram
        
        # 检查是否 OOM (Out Of Memory)
        if self.used_vram + size_bytes > self.vram_limit:
            raise MemoryError(
                f"CUDA OOM! Rank {self.rank} tried to allocate {size_bytes/1024**3:.2f}GB "
                f"for '{name}' but only has {available/1024**3:.2f}GB free. "
                f"Used: {self.used_vram/1024**3:.2f}/{self.vram_limit/1024**3:.2f}GB"
            )
        self.used_vram += size_bytes
        self.peak_vram = max(self.peak_vram, self.used_vram)

    def free(self, size_bytes, name="Tensor"):
        """模拟显存释放 (free)"""
        self.used_vram = max(0, self.used_vram - size_bytes)

    def stats(self):
        return f"Peak VRAM: {self.peak_vram/1024**3:.2f}GB | Limit: {self.vram_limit/1024**3:.2f}GB"

class MockNCCL:
    """模拟 NCCL 通信库 (Network Communication)"""
    def __init__(self, bandwidth_gbps=10.0):
        # 模拟带宽：10 GB/s (对于 PCIe 来说差不多，对于 NVLink 来说太慢)
        self.bandwidth = bandwidth_gbps * 1024 * 1024 * 1024 

    def all_gather(self, local_shard_size, world_size):
        """
        All-Gather 操作:
        每张卡把自己手里那 1/N 的碎片广播给所有人。
        最终结果：每张卡都凑齐了完整的数据。
        代价：巨大的通信量。
        """
        # 每个 Rank 接收来自其他 (N-1) 个 Rank 的数据
        total_data = local_shard_size * (world_size - 1)
        latency = total_data / self.bandwidth
        
        # 模拟网络抖动 jitter
        jitter = random.uniform(0.01, 0.05)
        # 模拟阻塞时间：CPU 此时在等数据，啥都干不了
        time.sleep(latency + jitter)
        return latency + jitter

    def reduce_scatter(self, local_shard_size, world_size):
        """
        Reduce-Scatter 操作:
        每张卡算出来的梯度是完整的，需要切碎了分发给其他人。
        最终结果：每张卡只保留了属于自己那一小块参数的梯度。
        """
        total_data = local_shard_size * (world_size - 1)
        latency = total_data / self.bandwidth
        jitter = random.uniform(0.01, 0.05)
        time.sleep(latency + jitter)
        return latency + jitter

def simulate_training(mode, world_size, model_size_gb=70.0):
    logger.info(f"🚀 Starting Simulation: Mode={mode.upper()}, World={world_size}, Model={model_size_gb}GB")
    
    # 模拟一张 24GB 的 GPU (比如 RTX 3090 / 4090)
    # 我们故意要跑 70GB 的模型，看看会发生什么
    GPU_LIMIT_GB = 24.0
    gpu = MockGPU(rank=0, vram_limit_gb=GPU_LIMIT_GB)
    
    # 5 GB/s 的模拟带宽
    nccl = MockNCCL(bandwidth_gbps=5.0) 

    model_size_bytes = model_size_gb * 1024 * 1024 * 1024
    
    try:
        # --- Phase 1: Model Initialization (模型加载阶段) ---
        if mode == "ddp":
            # DDP (Data Distributed Parallel): 也就是 PyTorch 默认模式
            # 这里的规则是：每张卡必须加载完整的模型副本！
            logger.info("📦 [Init] Loading Full Model weights (Replicated)...")
            gpu.allocate(model_size_bytes, "Full Model Weights") # 直接申请 70GB -> 必炸
        elif mode == "fsdp":
            # FSDP (Fully Sharded Data Parallel) / ZeRO-3
            # 规则：模型被切成 N 份，我只加载我的那一份。
            shard_size = model_size_bytes / world_size
            logger.info(f"📦 [Init] Loading Local Shard (1/{world_size})... Size: {shard_size/1024**3:.2f}GB")
            gpu.allocate(shard_size, "Model Shard") # 只申请 70/8 = 8.75GB -> 安全
            
        logger.info(f"✅ Model Loaded. {gpu.stats()}")
        
        # --- Phase 2: Forward Pass (前向传播) ---
        LAYERS = 24  # 假设模型有 24 层 Transformer Block
        layer_size = model_size_bytes / LAYERS
        
        start_time = time.time()
        logger.info("🔄 Start Forward Pass...")
        
        for i in range(LAYERS):
            # 激活值 (Activations) 必须保留以供反向传播使用
            # 假设激活值大小是参数量的 1/10
            # [动作 1] 产生“记忆” (Activations)
            # 这一层算出来的结果（激活值）必须留着！因为等会儿反向传播求导数要用。
            # 这是无法节省的固定开销。
            act_size = layer_size * 0.1
            gpu.allocate(act_size, f"L{i}_Activations")

            if mode == "fsdp":
                # FSDP 核心魔法：【借 -> 用 -> 还】三部曲
                
                # [背景]：
                # 我手里只有这层汉堡肉的 1/8 (local shard)。
                # 但要算这层，我手里必须有完整的汉堡肉。
                layer_shard = layer_size / world_size
                gathered_size = layer_shard * (world_size - 1)
                
                # 模拟通信开销 (Latency)
                latency = nccl.all_gather(layer_shard, world_size)
                
                # 临时分配显存给完整参数 (Transient Weights)
                gpu.allocate(gathered_size, f"L{i}_Transient_Weights")
                
                # 模拟计算 (Compute)
                time.sleep(0.05) 
                
                # 算完立刻释放！绝不留着占地方
                gpu.free(gathered_size, f"L{i}_Transient_Weights")
            else:
                # DDP: 参数本来就在这里，不需要通信，直接算
                time.sleep(0.05)
            
            if i % 8 == 0:
                logger.info(f"   ➡️ Processed Layer {i}/{LAYERS} | VRAM: {gpu.used_vram/1024**3:.1f}GB")

        logger.info("🛑 Forward Done. Start Backward Pass...")

        # --- Phase 3: Backward Pass (反向传播) ---
        for i in range(LAYERS - 1, -1, -1):
            if mode == "fsdp":
                # 反向传播时，又需要参数来算梯度，所以得再拉一次！(All-Gather)
                # 算术题（为什么大家都说通信是瓶颈？）：
                # 假设有 8 张卡 (world_size=8)，模型这一层大小是 800MB。
                # 1. layer_shard: 我自己只存了 1/8 (100MB)。
                # 2. gathered_size: 为了凑齐 800MB，我必须从另外 7 个人手里下载 700MB！
                #    公式: gathered_size = 100MB * (8 - 1)
                layer_shard = layer_size / world_size
                gathered_size = layer_shard * (world_size - 1)
                
                # 1. 再次 All-Gather 拿参数
                nccl.all_gather(layer_shard, world_size)
                gpu.allocate(gathered_size, f"L{i}_Transient_Weights_Bwd")

                # [动作 1.5]: 计算梯度 (Compute Gradients)
                # 刚才 user 问这步去哪了？其实之前代码里把这步省略了。
                # 只有拿到完整参数后，才能通过链式法则 (Chain Rule) 算出这层的梯度。
                # Backward 计算量和 Forward 差不多，甚至更大一点。
                time.sleep(0.05) 
                
                # 2. Reduce-Scatter 聚合梯度 (这是 All-Gather 的逆过程)
                # [背景]: 
                # 现在每张卡都算出了这层网络完整的梯度 (Gradient)。
                # 但根据 FSDP 规则，我只负责维护这层参数的 1/8。
                # 所以我不需要保存所有的梯度，我只需要保存属于我的那 1/8 的梯度。
                
                # [动作]:
                # 1. Reduce (求和): 把所有卡上算出来的梯度加在一起（因为是 Distributed Data Parallel，梯度要取平均/和）。
                # 2. Scatter (分发): 加完之后，把结果切成 8 份。
                #    - 第 1 份发给卡 1
                #    - 第 2 份发给卡 2
                #    ...
                # [结果]:
                # 通信完后，我手里就只剩下了属于我负责的那 1/8 梯度。显存再次释放。
                nccl.reduce_scatter(layer_shard, world_size)
                
                # 3. 释放参数
                gpu.free(gathered_size, f"L{i}_Transient_Weights_Bwd")
            
            # 这一层的激活值用完了，释放
            act_size = layer_size * 0.1
            gpu.free(act_size, f"L{i}_Activations")

        
        logger.info("✅ Training Step Complete!")
        total_time = time.time() - start_time
        logger.info(f"📊 Summary:")
        logger.info(f"   - Mode: {mode.upper()}")
        logger.info(f"   - GPUs: {world_size}")
        logger.info(f"   - Peak VRAM: {gpu.peak_vram/1024**3:.2f} GB (Limit: {GPU_LIMIT_GB} GB)")
        logger.info(f"   - Time: {total_time:.2f}s")
        
    except MemoryError as e:
        logger.error(f"💥 {str(e)}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["ddp", "fsdp"], required=True)
    parser.add_argument("--world_size", type=int, default=1)
    args = parser.parse_args()
    
    simulate_training(args.mode, args.world_size)
