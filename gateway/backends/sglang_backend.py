import asyncio
import json
import urllib.request
import functools

class SGLangBackend:
    def __init__(self, endpoint="http://localhost:8001/v1/chat/completions"):
        self.endpoint = endpoint

    async def _run_sync(self, func, *args, **kwargs):
        loop = asyncio.get_event_loop()
        pfunc = functools.partial(func, *args, **kwargs)
        return await loop.run_in_executor(None, pfunc)
    
    async def create_pod(self, sandbox_id, image, runtime_class=None):
        """
        Virtual session for SGLang.
        """
        pod_name = f"sglang-{sandbox_id}"
        print(f"🔹 [SGLang] Using Engine: {self.endpoint}")
        return pod_name

    async def exec_command(self, pod_name, cmd):
        """
        Executes a Prompt on SGLang.
        """
        print(f"🔹 [SGLang] Requesting. Prompt: {cmd[:50]}...")
        
        payload = {
            "model": "mock-sglang",
            "messages": [{"role": "user", "content": cmd}],
            "max_tokens": 100,
            "stream": False 
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
            resp_str = await self._run_sync(_request)
            
            if resp_str.startswith("Error"):
                return f"❌ SGLang Engine Error: {resp_str}"

            # SGLang mock response format logic
            # Note: Our mock only implemented streaming for now, 
            # let's quick fix the Mock or handle streaming here?
            # Actually, let's assume the mock WILL support non-streaming 
            # OR we implement simple stream consumption here.
            
            # IF the mock returns explicit error "Mock supports streaming only", handle it.
            if "streaming only" in resp_str:
                 return "⚠️ Error: Backend requires streaming (not implemented in this minimal client)"

            resp_json = json.loads(resp_str)
            # Check for error
            if "error" in resp_json:
                 return f"❌ SGLang Error: {resp_json['error']}"

            content = resp_json['choices'][0]['message']['content']
            return content
            
        except Exception as e:
            return f"❌ Backend Logic Error: {e}"
