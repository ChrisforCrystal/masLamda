import asyncio
import time
import sys
import os

# Add project root to path to import backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from gateway.backends.vllm_backend import VLLMBackend

async def run_benchmark(concurrency=20):
    print(f"🚀 Starting vLLM Continuous Batching Benchmark")
    print(f"🔹 Concurrency: {concurrency} requests")
    print(f"🔹 Engine Limit: 10 Slots (Simulated H100)")
    print("-" * 50)

    backend = VLLMBackend(endpoint="http://localhost:8000/v1/chat/completions")
    
    start_time = time.time()
    
    async def worker(i):
        # Create a prompt of variable length to simulate real workload
        prompt_len = (i % 5) + 1
        prompt = "Hello " * prompt_len
        
        # Virtual "Pod Creation" (Session Init)
        pod_name = await backend.create_pod(f"req-{i}", "vllm-image")
        
        # Inference
        try:
            response = await backend.exec_command(pod_name, prompt)
            print(f"✅ Req {i:02d} Finished: {len(response)} chars")
            return True
        except Exception as e:
            print(f"❌ Req {i:02d} Failed: {e}")
            return False

    # Launch all requests effectively at once
    tasks = [worker(i) for i in range(concurrency)]
    results = await asyncio.gather(*tasks)
    
    total_time = time.time() - start_time
    success_count = sum(results)
    
    print("-" * 50)
    print(f"🏁 Benchmark Complete")
    print(f"⏱️  Total Time: {total_time:.2f}s")
    print(f"📦 Throughput: {concurrency / total_time:.2f} req/s")
    print(f"✅ Success Rate: {success_count}/{concurrency}")
    
    # Analysis
    if total_time < (concurrency * 0.1): # Rough check
        print("\n🧐 IMPACT ANALYSIS:")
        print("   If this were serial processing, it would take much longer.")
        print("   The Continuous Batching scheduler allowed 'waiting' requests")
        print("   to immediately fill slots released by finished requests.")

if __name__ == "__main__":
    try:
        asyncio.run(run_benchmark())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Benchmark failed: {e}")
