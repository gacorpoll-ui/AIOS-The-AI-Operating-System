import pytest
import asyncio
import time
from unittest.mock import MagicMock
from agent.core.system_watcher import SystemWatcher, SystemState
from agent.core.ipc import IPCServer, IPCClient

class TestDaemon:
    
    @pytest.mark.asyncio
    async def test_ipc_client_server_communication(self):
        # We need a free port for TCP or unique socket path
        server = IPCServer(tcp_port=40505)
        
        def mock_handler(req):
            if req["type"] == "ping":
                return {"pong": True}
            raise ValueError("Unknown")
            
        server.set_handler(mock_handler)
        await server.start_server()
        
        try:
            client = IPCClient(tcp_port=40505)
            
            # Test success
            res = await client.send_async("ping", {})
            assert res["success"] is True
            assert res["data"]["pong"] is True
            
            # Test error handling
            res2 = await client.send_async("unknown", {})
            assert res2["success"] is False
            assert "Unknown" in res2["error"]
        finally:
            await server.stop_server()
            
    def test_system_watcher_returns_state(self):
        watcher = SystemWatcher()
        state = watcher.get_current_state()
        
        assert isinstance(state, SystemState)
        assert hasattr(state, "cpu_percent")
        assert hasattr(state, "memory_percent")
        assert state.timestamp > 0
        
    def test_anomaly_detection_fires(self):
        watcher = SystemWatcher()
        
        # Simulate sustained high CPU
        for i in range(5):
            state = SystemState(time.time(), 95.0, 50.0, 50.0, 10, 100)
            watcher.history.append(state)
            
        anomalies = watcher.detect_anomaly(state)
        assert len(anomalies) > 0
        assert any(a.type == "High CPU" for a in anomalies)
