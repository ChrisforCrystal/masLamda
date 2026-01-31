from kubernetes import client, config, stream
from kubernetes.client.rest import ApiException
import asyncio
import functools

# Load K8S Config
try:
    config.load_incluster_config()
    print("🔹 Loaded In-Cluster Config")
except:
    config.load_kube_config()
    # Debug: Print loaded host to verify connection
    print(f"🔹 Loaded Kube Config. Active Host: {client.Configuration.get_default_copy().host}")

v1 = client.CoreV1Api()

class K8SBackend:
    def __init__(self):
        pass

    async def _run_sync(self, func, *args, **kwargs):
        loop = asyncio.get_event_loop()
        pfunc = functools.partial(func, *args, **kwargs)
        return await loop.run_in_executor(None, pfunc)

    async def create_pod(self, sandbox_id, image, runtime_class=None):
        pod_name = f"sb-{sandbox_id}"
        
        # Logic to differentiate WASM vs Container
        cmd = ["/bin/sh", "-c", "sleep 3600"] # Default for Container
        if runtime_class and "wasm" in runtime_class:
            cmd = None # WASM runs its own entrypoint
        
        # Determine Pod Spec based on Runtime
        # gVisor/Standard Pods need a shell loop to stay alive for 'exec'
        
        container = client.V1Container(
            name="sandbox",
            image=image,
            image_pull_policy="IfNotPresent"
        )
        if cmd:
            container.command = cmd
        
        # [Fix] Wasm Edge Example listens on 8080. 
        # Explicitly exposing it helps some CNIs/Setup.
        if runtime_class and "wasm" in runtime_class:
            container.ports = [client.V1ContainerPort(container_port=8080)]
        
        spec = client.V1PodSpec(containers=[container], restart_policy="Never")
        if runtime_class:
            spec.runtime_class_name = runtime_class

        # [Kueue Integration]
        # Assign this Pod to the 'sandbox-lq' queue.
        # Kueue webhook will intercept this Pod, suspend it, and manage its quota.
        labels = {
            "app": "sandbox",
            "kueue.x-k8s.io/queue-name": "sandbox-lq" 
        }

        pod = client.V1Pod(
            metadata=client.V1ObjectMeta(name=pod_name, labels=labels),
            spec=spec
        )

        try:
            print(f"🚀 Creating Pod {pod_name} (Runtime: {runtime_class})...")
            await self._run_sync(v1.create_namespaced_pod, namespace="default", body=pod)
            
            # Helper to check status
            def check_status():
                return v1.read_namespaced_pod(name=pod_name, namespace="default")

            # Simple wait loop
            for _ in range(30): # 30 seconds timeout
                p = await self._run_sync(check_status)
                if p.status.phase == "Running":
                    print(f"✅ Pod {pod_name} is Running!")
                    return pod_name
                await asyncio.sleep(1)
            
            raise Exception(f"Timeout waiting for Pod {pod_name} to start")
            
        except ApiException as e:
            print(f"❌ K8S Error: {e}")
            raise

    async def exec_command(self, pod_name, cmd):
        def _exec():
            # stream() is blocking
            return stream.stream(v1.connect_get_namespaced_pod_exec,
                                 pod_name,
                                 'default',
                                 command=['/bin/sh', '-c', cmd],
                                 stderr=True, stdin=False,
                                 stdout=True, tty=False)

        # Run blocking call in executor
        loop = asyncio.get_event_loop()
        output = await loop.run_in_executor(None, _exec)
        return output
