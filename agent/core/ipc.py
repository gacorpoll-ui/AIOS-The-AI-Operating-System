import json
import asyncio
import logging
import socket
import os
from typing import Dict, Any, Callable, Optional

logger = logging.getLogger(__name__)

class IPCServer:
    """Unix socket/TCP server for IPC."""
    
    def __init__(self, socket_path: str = "/tmp/aios.sock", tcp_port: int = 40500):
        self.socket_path = socket_path
        self.tcp_port = tcp_port
        self.handler: Optional[Callable] = None
        self.server = None
        
    def set_handler(self, handler: Callable[[Dict[str, Any]], Dict[str, Any]]):
        self.handler = handler
        
    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            data = await reader.readline()
            if not data:
                return
                
            request_str = data.decode('utf-8').strip()
            
            try:
                request = json.loads(request_str)
            except json.JSONDecodeError:
                response = {"id": "unknown", "success": False, "data": None, "error": "Invalid JSON"}
            else:
                if self.handler:
                    try:
                        response_data = self.handler(request)
                        response = {
                            "id": request.get("id", "unknown"),
                            "success": True,
                            "data": response_data,
                            "error": None,
                            "version": "1.0"
                        }
                    except Exception as e:
                        response = {
                            "id": request.get("id", "unknown"),
                            "success": False,
                            "data": None,
                            "error": str(e),
                            "version": "1.0"
                        }
                else:
                    response = {"id": request.get("id", "unknown"), "success": False, "data": None, "error": "No handler configured"}
                    
            writer.write((json.dumps(response) + "\n").encode('utf-8'))
            await writer.drain()
            
        except Exception as e:
            logger.error(f"IPC error: {e}")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
                
    async def start_server(self):
        """Starts the IPC server."""
        # Use TCP on Windows since Unix sockets aren't uniformly supported
        if os.name == 'nt':
            self.server = await asyncio.start_server(self._handle_client, '127.0.0.1', self.tcp_port)
            logger.info(f"IPC Server started on 127.0.0.1:{self.tcp_port}")
        else:
            # Unix environment
            if os.path.exists(self.socket_path):
                os.unlink(self.socket_path)
            self.server = await asyncio.start_unix_server(self._handle_client, self.socket_path)
            logger.info(f"IPC Server started on {self.socket_path}")
            
    async def stop_server(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            if os.name != 'nt' and os.path.exists(self.socket_path):
                os.unlink(self.socket_path)

class IPCClient:
    """Client to connect to the IPC server."""
    
    def __init__(self, socket_path: str = "/tmp/aios.sock", tcp_port: int = 40500):
        self.socket_path = socket_path
        self.tcp_port = tcp_port
        
    async def send_async(self, request_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Sends request asynchronously."""
        import uuid
        request = {
            "id": str(uuid.uuid4()),
            "type": request_type,
            "payload": payload,
            "version": "1.0"
        }
        
        try:
            if os.name == 'nt':
                reader, writer = await asyncio.open_connection('127.0.0.1', self.tcp_port)
            else:
                reader, writer = await asyncio.open_unix_connection(self.socket_path)
                
            writer.write((json.dumps(request) + "\n").encode('utf-8'))
            await writer.drain()
            
            data = await reader.readline()
            writer.close()
            await writer.wait_closed()
            
            if not data:
                return {"success": False, "error": "Empty response"}
                
            return json.loads(data.decode('utf-8'))
            
        except ConnectionRefusedError:
            return {"success": False, "error": "Daemon is not running"}
        except Exception as e:
            return {"success": False, "error": str(e)}
            
    def send(self, request_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous wrapper for send_async."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        return loop.run_until_complete(self.send_async(request_type, payload))
