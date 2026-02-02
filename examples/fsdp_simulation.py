import time
import argparse
import sys
import logging
import random

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [Rank %(process)d] %(message)s")
logger = logging.getLogger("fsdp-sim")

class MockGPU:
    def __init__(self, rank, vram_limit_gb=16.0):
        self.rank = rank
        self.vram_limit = vram_limit_gb * 1024 * 1024 * 1024  # Bytes
        self.used_vram = 0
        self.peak_vram = 0

    def allocate(self, size_bytes, name="Tensor"):
        required = size_bytes
        available = self.vram_limit - self.used_vram
        
        if self.used_vram + size_bytes > self.vram_limit:
            raise MemoryError(
                f"CUDA OOM! Rank {self.rank} tried to allocate {size_bytes/1024**3:.2f}GB "
                f"for '{name}' but only has {available/1024**3:.2f}GB free. "
                f"Used: {self.used_vram/1024**3:.2f}/{self.vram_limit/1024**3:.2f}GB"
            )
        self.used_vram += size_bytes
        self.peak_vram = max(self.peak_vram, self.used_vram)
        # Low verbosity for individual allocs to keep logs clean
        # logger.debug(f"Allocated {size_bytes/1024**3:.2f}GB for {name}. Usage: {self.used_vram/1024**3:.2f}GB")

    def free(self, size_bytes, name="Tensor"):
        self.used_vram = max(0, self.used_vram - size_bytes)
        # logger.debug(f"Freed {size_bytes/1024**3:.2f}GB for {name}. Usage: {self.used_vram/1024**3:.2f}GB")

    def stats(self):
        return f"Peak VRAM: {self.peak_vram/1024**3:.2f}GB | Limit: {self.vram_limit/1024**3:.2f}GB"

class MockNCCL:
    def __init__(self, bandwidth_gbps=10.0):
        # 10 GB/s bandwidth
        self.bandwidth = bandwidth_gbps * 1024 * 1024 * 1024 

    def all_gather(self, local_shard_size, world_size):
        # In All-Gather, each rank receives shards from all other (N-1) ranks
        # Total data volume entering this node
        total_data = local_shard_size * (world_size - 1)
        latency = total_data / self.bandwidth
        # Add random jitter
        jitter = random.uniform(0.01, 0.05)
        time.sleep(latency + jitter)
        return latency + jitter

    def reduce_scatter(self, local_shard_size, world_size):
        # Similar volume for Reduce-Scatter
        total_data = local_shard_size * (world_size - 1)
        latency = total_data / self.bandwidth
        jitter = random.uniform(0.01, 0.05)
        time.sleep(latency + jitter)
        return latency + jitter

def simulate_training(mode, world_size, model_size_gb=70.0):
    logger.info(f"🚀 Starting Simulation: Mode={mode.upper()}, World={world_size}, Model={model_size_gb}GB")
    
    # Simulate a 24GB GPU (e.g., RTX 3090 / 4090)
    # We want to show OOM on 70GB model
    GPU_LIMIT_GB = 24.0
    gpu = MockGPU(rank=0, vram_limit_gb=GPU_LIMIT_GB)
    
    # 5 GB/s simulated bandwidth (PCIe Gen4 ish)
    nccl = MockNCCL(bandwidth_gbps=5.0) 

    model_size_bytes = model_size_gb * 1024 * 1024 * 1024
    
    try:
        # --- Phase 1: Model Initialization ---
        if mode == "ddp":
            logger.info("📦 [Init] Loading Full Model weights (Replicated)...")
            gpu.allocate(model_size_bytes, "Full Model Weights")
        elif mode == "fsdp":
            shard_size = model_size_bytes / world_size
            logger.info(f"📦 [Init] Loading Local Shard (1/{world_size})... Size: {shard_size/1024**3:.2f}GB")
            gpu.allocate(shard_size, "Model Shard")
            
        logger.info(f"✅ Model Loaded. {gpu.stats()}")
        
        # --- Phase 2: Forward Pass (Layer by Layer) ---
        LAYERS = 24  # Iterate through layers
        layer_size = model_size_bytes / LAYERS
        
        start_time = time.time()
        logger.info("🔄 Start Forward Pass...")
        
        for i in range(LAYERS):
            # Compute Input Activation (Persistent for Backprop)
            # Assumption: Activations are 1/10th of layer size
            act_size = layer_size * 0.1
            gpu.allocate(act_size, f"L{i}_Activations")

            if mode == "fsdp":
                # ZeRO-3: All-Gather full layer weights on demand
                layer_shard = layer_size / world_size
                gathered_size = layer_shard * (world_size - 1)
                
                # logger.info(f"   [L{i}] All-Gathering weights ({gathered_size/1024**3:.2f}GB)...")
                latency = nccl.all_gather(layer_shard, world_size)
                
                # Allocate Transient Weights
                gpu.allocate(gathered_size, f"L{i}_Transient_Weights")
                
                # Simulate Compute
                time.sleep(0.05) 
                
                # Free Transient Weights immediately
                gpu.free(gathered_size, f"L{i}_Transient_Weights")
            else:
                # DDP: Weights already there
                time.sleep(0.05)
            
            if i % 8 == 0:
                logger.info(f"   ➡️ Processed Layer {i}/{LAYERS} | VRAM: {gpu.used_vram/1024**3:.1f}GB")

        logger.info("🛑 Forward Done. Start Backward Pass...")

        # --- Phase 3: Backward Pass ---
        for i in range(LAYERS - 1, -1, -1):
            if mode == "fsdp":
                # ZeRO-3 Again: Need weights for gradient computation
                layer_shard = layer_size / world_size
                gathered_size = layer_shard * (world_size - 1)
                
                # All-Gather
                nccl.all_gather(layer_shard, world_size)
                gpu.allocate(gathered_size, f"L{i}_Transient_Weights_Bwd")
                
                # Reduce Scatter Gradients (Communication)
                # We assume gradient size ~= weight size
                nccl.reduce_scatter(layer_shard, world_size)
                
                # Free Transient Weights
                gpu.free(gathered_size, f"L{i}_Transient_Weights_Bwd")
            
            # Free Activations
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
