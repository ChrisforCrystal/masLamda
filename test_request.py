import requests
try:
    files = {'file': open('echo.wat', 'rb')}
    data = {'input': 'Hello Wasm Service!'}
    print("Sending request...")
    r = requests.post('http://127.0.0.1:8999/run_with_input', files=files, data=data, timeout=10)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text}")
except Exception as e:
    print(f"Error: {e}")
