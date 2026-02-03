import ray
import torch
import time

# 连接到 Ray Cluster
# 在 K8s 内部运行时，通常会自动发现 Ray Head
ray.init()

print("🚀 Connected to Heterogeneous Ray Cluster!")
print(f"Nodes: {len(ray.nodes())}")

# --- Task 1: Run on NVIDIA GPU (via Hami vGPU) ---
# 请求自定义资源：hami.io/vgpu-memory (单位 MiB)
# 注意：这里为了演示，假设我们在 Python 代码里显式请求这些资源
@ray.remote(resources={"hami.io/vgpu-memory": 1000}) 
def run_on_nvidia():
    import torch
    print(f"🟢 [NVIDIA] Running on Device: {torch.cuda.get_device_name(0)}")
    # 模拟训练
    a = torch.randn(1000, 1000).cuda()
    b = torch.randn(1000, 1000).cuda()
    c = torch.matmul(a, b)
    return "NVIDIA Success"

# --- Task 2: Run on Huawei Ascend NPU ---
# 请求华为 NPU 资源
@ray.remote(resources={"huawei.com/Ascend910": 1})
def run_on_ascend():
    # 华为 PyTorch 插件通常叫 torch_npu
    try:
        import torch_npu 
        device_name = torch.npu.get_device_name(0)
    except ImportError:
        device_name = "Mock Ascend NPU (No Driver Found)"
        
    print(f"🔴 [Huawei] Running on Device: {device_name}")
    # 模拟训练
    # device = torch.device('npu:0')
    # a = torch.randn(1000, 1000).to(device)
    return "Ascend Success"

# --- Task 3: Run on Cambricon MLU ---
# 请求寒武纪 MLU 资源
@ray.remote(resources={"cambricon.com/mlu": 1})
def run_on_mlu():
    try:
        import torch_mlu
        device_name = torch.mlu.get_device_name(0)
    except ImportError:
        device_name = "Mock MLU (No Driver Found)"
        
    print(f"🔵 [Cambricon] Running on Device: {device_name}")
    return "MLU Success"

# Submit Tasks
print("\nDispatcher: Submitting tasks to heterogeneous workers...")
future_nvidia = run_on_nvidia.remote()
future_ascend = run_on_ascend.remote()
future_mlu = run_on_mlu.remote()

# Wait for results
results = ray.get([future_nvidia, future_ascend, future_mlu])
print(f"\n✅ All Tasks Completed: {results}")
