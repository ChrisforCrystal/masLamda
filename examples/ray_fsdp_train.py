import ray
import ray.train
from ray.train import ScalingConfig
from ray.train.torch import TorchTrainer
import time
import os
import socket
import psutil

def train_func(config):
    # --- 1. RDMA 接口检查 ---
    # 在真实训练开始前，必须确认 RDMA 网卡 (net1) 已经挂载
    interfaces = psutil.net_if_addrs()
    has_rdma = "net1" in interfaces or "ib0" in interfaces
    
    worker_rank = ray.train.get_context().get_world_rank()
    print(f"🚀 [Rank {worker_rank}] Network Interfaces: {list(interfaces.keys())}")
    
    if not has_rdma:
        print(f"⚠️ [Rank {worker_rank}] WARNING: RDMA interface (net1/ib0) NOT found! Falling back to TCP (slow).")
    else:
        print(f"✅ [Rank {worker_rank}] RDMA Interface Detected! Ready for high-speed NCCL.")

    # --- 2. 模拟 FSDP 训练循环 ---
    # 这里我们复用之前的 fsdp_simulation 逻辑，但是放在 Ray Train 的上下文里
    world_size = ray.train.get_context().get_world_size()
    
    print(f"🔥 [Rank {worker_rank}] Starting FSDP Training (Simulated) with World Size {world_size}")
    
    for epoch in range(3):
        print(f"🔄 [Rank {worker_rank}] Epoch {epoch} Start...")
        
        # 模拟 Forward/Backward
        # 真实代码里这里会是 model(input) 和 loss.backward()
        # 此时 NCCL 会疯狂地在 net1 上交换数据
        time.sleep(1.0) 
        
        print(f"✅ [Rank {worker_rank}] Epoch {epoch} Done. Reporting metrics.")
        ray.train.report({"loss": 0.1 * (3 - epoch), "epoch": epoch})

def main():
    ray.init()
    
    print("📦 Submitting Ray Train Job...")
    
    # 定义我们要用多少个 Worker (GPUs)
    # ScalingConfig 会请求 K8s 调度相应数量的 Pod
    trainer = TorchTrainer(
        train_loop_per_worker=train_func,
        scaling_config=ScalingConfig(
            num_workers=4, # 4 卡分布式训练
            use_gpu=True,  # 请求 GPU
            resources_per_worker={"CPU": 1, "GPU": 1}
        )
    )
    
    result = trainer.fit()
    print(f"🎉 Training Completed! Result: {result.metrics}")

if __name__ == "__main__":
    main()
