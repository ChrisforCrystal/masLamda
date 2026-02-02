import asyncio
import json
import urllib.request
import functools

class VLLMBackend:
    def __init__(self, endpoint="http://localhost:8000/v1/chat/completions"):
        self.endpoint = endpoint

    async def _run_sync(self, func, *args, **kwargs):
        loop = asyncio.get_event_loop()
        pfunc = functools.partial(func, *args, **kwargs)
        return await loop.run_in_executor(None, pfunc)
    
    async def create_pod(self, sandbox_id, image, runtime_class=None):
        """
        In the vLLM context, we don't spin up a new container for each request.
        The 'Cluster' (vLLM Engine) is always running.
        This method acts as a virtual session initializer or health check.
        """
        # Generate a virtual ID.
        pod_name = f"vllm-{sandbox_id}"
        print(f"🔹 [VLLM] Initializing virtual session {pod_name} (Using Engine: {self.endpoint})")
        return pod_name

    async def exec_command(self, pod_name, cmd):
        """
        Executes a 'Command'. 
        In the context of an Inference Backend, the command IS the PROMPT.
        """
        print(f"🔹 [VLLM] Requesting Inference. Prompt: {cmd[:50]}...")
        
        # Construct OpenAI-compatible request body
        payload = {
            "model": "mock-gpt",
            "messages": [{"role": "user", "content": cmd}],
            "max_tokens": 100, # Generate a reasonable amount of text
            "stream": False    # For this MVP, we use blocking wait to match 'exec' behavior
        }
        
        def _request():
            try:
                req = urllib.request.Request(
                    self.endpoint, 
                    data=json.dumps(payload).encode('utf-8'),
                    headers={'Content-Type': 'application/json'}
                )
                with urllib.request.urlopen(req) as response:
                    return response.read().decode('utf-8')
            except Exception as e:
                return str(e)

        try:
            # Perform HTTP Request in ThreadPool
            resp_str = await self._run_sync(_request)
            
            # Simple error handling
            if resp_str.startswith("Error") or "Connection refused" in resp_str:
                return f"❌ vLLM Engine Error: {resp_str}"

            # Parse OpenAI Response
            resp_json = json.loads(resp_str)
            content = resp_json['choices'][0]['message']['content']
            return content
            
        except Exception as e:
            return f"❌ Gateway Logic Error: {e}"
