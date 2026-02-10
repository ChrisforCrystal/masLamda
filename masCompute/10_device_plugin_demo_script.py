import json
import logging
import os
import signal
import socket
import sys
import time
from concurrent import futures

import grpc

# Note: These imports require generating the gRPC code from v1beta1/api.proto
# Command: python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. api.proto
# For this demo to work, you would need the generated device_plugin_pb2 and device_plugin_pb2_grpc
try:
    import device_plugin_pb2
    import device_plugin_pb2_grpc
except ImportError:
    # Handle the case where protos are not compiled so the script can still be read/understood
    class MockProto:
        def __getattr__(self, _): return None
    device_plugin_pb2 = MockProto()
    device_plugin_pb2_grpc = MockProto()

# Configuration
RESOURCE_NAME = "example.com/demo-resource"
CONFIG_FILE = "/etc/demo-resource/config.json"
KUBELET_SOCKET = "/var/lib/kubelet/device-plugins/kubelet.sock"
PLUGIN_SOCKET = "/var/lib/kubelet/device-plugins/demo-plugin.sock"

class DemoDevicePlugin(device_plugin_pb2_grpc.DevicePluginServicer):
    def __init__(self):
        self.devices = self._load_devices_from_file()

    def _load_devices_from_file(self):
        """Reads resource count from a local file."""
        devices = []
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    cnt = json.load(f).get("count", 0)
                    for i in range(cnt):
                        devices.append(device_plugin_pb2.Device(
                            ID=f"demo-dev-{i}",
                            Health=device_plugin_pb2.Healthy
                        ))
            else:
                logging.warning(f"Config file {CONFIG_FILE} not found, reporting 0 devices")
        except Exception as e:
            logging.error(f"Error reading config: {e}")
        return devices

    def GetDevicePluginOptions(self, request, context):
        return device_plugin_pb2.DevicePluginOptions(PreStartRequired=False)

    def ListAndWatch(self, request, context):
        """Streaming method that sends device state to Kubelet."""
        logging.info("ListAndWatch started")
        while True:
            # In a real plugin, you might watch the file for changes here
            response = device_plugin_pb2.ListAndWatchResponse(devices=self.devices)
            yield response
            time.sleep(10) # Simple periodic update

    def Allocate(self, request, context):
        """Called when a container requests this resource."""
        logging.info("Allocate called")
        response = device_plugin_pb2.AllocateResponse()
        for req in request.ContainerRequests:
            container_response = device_plugin_pb2.ContainerAllocateResponse()
            # Here you would typically inject environment variables or mount device files
            # For this demo, we just set a dummy ENV
            container_response.Envs["DEMO_RESOURCE_ID"] = ",".join(req.DevicesIDs)
            response.ContainerResponses.append(container_response)
        return response

    def PreStartContainer(self, request, context):
        return device_plugin_pb2.PreStartContainerResponse()

def register_with_kubelet():
    """Connects to Kubelet socket and registers this plugin."""
    logging.info("Registering with Kubelet...")
    channel = grpc.insecure_channel(f'unix://{KUBELET_SOCKET}')
    stub = device_plugin_pb2_grpc.RegistrationStub(channel)
    request = device_plugin_pb2.RegisterRequest(
        Version="v1beta1",
        Endpoint=os.path.basename(PLUGIN_SOCKET),
        ResourceName=RESOURCE_NAME,
        Options=device_plugin_pb2.DevicePluginOptions(PreStartRequired=False)
    )
    stub.Register(request)
    logging.info("Successfully registered!")

def serve():
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
    
    # 1. Start gRPC server
    if os.path.exists(PLUGIN_SOCKET):
        os.remove(PLUGIN_SOCKET)
        
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    device_plugin_pb2_grpc.add_DevicePluginServicer_to_server(DemoDevicePlugin(), server)
    server.add_insecure_port(f'unix://{PLUGIN_SOCKET}')
    server.start()
    
    # 2. Register with Kubelet
    # Wait for Kubelet socket if needed, then register
    time.sleep(2) 
    register_with_kubelet()
    
    logging.info("Device Plugin server running...")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.stop(0)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    serve()
