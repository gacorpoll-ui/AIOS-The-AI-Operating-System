import os
import asyncio
import logging
import signal
from typing import Dict, Any

from agent.models.llm_interface import LocalLLM
from agent.core.memory import MemoryEngine
from agent.core.context_manager import ContextManager
from agent.core.tool_registry import ToolRegistry
from security.monitor import SecurityMonitor
from agent.core.system_watcher import SystemWatcher
from agent.core.ipc import IPCServer

logger = logging.getLogger(__name__)

class AIOSDaemon:
    """The always-on background intelligence of AIOS."""
    
    def __init__(self):
        self.running = False
        self.llm = LocalLLM()
        # Mock paths for db
        os.makedirs(os.path.expanduser("~/.aios"), exist_ok=True)
        self.memory = MemoryEngine(db_path=os.path.expanduser("~/.aios/daemon_memory"))
        self.context = ContextManager(self.memory)
        self.tools = ToolRegistry(db_path=os.path.expanduser("~/.aios/daemon_tools.db"))
        self.security = SecurityMonitor()
        self.watcher = SystemWatcher()
        self.ipc = IPCServer()
        
    def _handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Routes IPC requests to appropriate handlers."""
        req_type = request.get("type")
        payload = request.get("payload", {})
        
        if req_type == "ping":
            return {"status": "pong", "system_state": self.watcher.get_current_state().__dict__}
        elif req_type == "shell_request":
            # In full implementation, this routes to orchestrator or NL shell interpreter
            # Here we just acknowledge receipt
            user_input = payload.get("input", "")
            return {"message": f"Daemon received: {user_input}. LLM loaded: {self.llm.is_loaded}"}
        elif req_type == "shutdown":
            # Note: in real async app, we'd signal an event instead of setting flag directly
            self.running = False
            return {"status": "shutting down"}
        else:
            raise ValueError(f"Unknown request type: {req_type}")
            
    async def _run_tasks(self):
        """Runs the main daemon background tasks."""
        self.ipc.set_handler(self._handle_request)
        await self.ipc.start_server()
        
        self.security.start()
        
        # Load LLM in background so it doesn't block startup
        # In a real app we'd use run_in_executor
        try:
            # We use the mock pattern here if the real one isn't available
            # self.llm.load(...)
            pass
        except Exception as e:
            logger.error(f"Failed to load LLM: {e}")
            
        logger.info("AIOS Daemon fully initialized")
        
        # Main watcher loop
        while self.running:
            state = self.watcher.get_current_state()
            anomalies = self.watcher.detect_anomaly(state)
            if anomalies:
                for a in anomalies:
                    logger.warning(f"Anomaly detected: {a.type} - {a.description}")
            await asyncio.sleep(2)  # Short sleep for testing, normally 30s
            
    async def _shutdown(self):
        """Graceful shutdown sequence."""
        logger.info("Shutting down AIOS Daemon...")
        self.security.stop()
        await self.ipc.stop_server()
        self.context.save_session()
        self.memory.close()
        logger.info("Shutdown complete")
        
    def start(self):
        """Entry point."""
        self.running = True
        
        # Handle termination signals gracefully
        loop = asyncio.get_event_loop()
        
        if os.name != 'nt':
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, lambda: setattr(self, 'running', False))
                
        try:
            loop.run_until_complete(self._run_tasks())
        except KeyboardInterrupt:
            self.running = False
        finally:
            loop.run_until_complete(self._shutdown())

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    daemon = AIOSDaemon()
    daemon.start()
