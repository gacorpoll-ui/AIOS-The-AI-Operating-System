import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from .memory import MemoryEngine

class ContextManager:
    """Maintains the 'working context' of the current session."""
    
    def __init__(self, memory_engine: MemoryEngine):
        self.memory_engine = memory_engine
        self.session_id: str = ""
        self.start_time: Optional[datetime] = None
        self.active_task: str = ""
        self.open_files: List[str] = []
        self.recent_commands: List[Dict[str, Any]] = []
        
    def start_session(self) -> str:
        """Initializes a new session."""
        self.session_id = str(uuid.uuid4())
        self.start_time = datetime.now(timezone.utc)
        self.active_task = ""
        self.open_files = []
        self.recent_commands = []
        return self.session_id
        
    def add_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Records an event in the session."""
        event = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.recent_commands.append(event)
        
        # Keep recent commands bounded
        if len(self.recent_commands) > 50:
            self.recent_commands.pop(0)
            
    def get_current_context(self) -> Dict[str, Any]:
        """Returns the current state."""
        duration = 0
        if self.start_time:
            duration = (datetime.now(timezone.utc) - self.start_time).total_seconds()
            
        return {
            "session_id": self.session_id,
            "active_task": self.active_task,
            "open_files": self.open_files,
            "recent_commands": self.recent_commands,
            "session_duration_seconds": duration
        }
        
    def save_session(self) -> None:
        """Persists session to MemoryEngine before shutdown."""
        if not self.session_id:
            return
            
        context_data = self.get_current_context()
        self.memory_engine.store(
            content=str(context_data),
            metadata={"session_id": self.session_id},
            memory_type="session_context"
        )
        # We also store the last session ID in KV for quick retrieval
        self.memory_engine.store_kv("last_session_id", self.session_id)
        
    def restore_last_session(self) -> Dict[str, Any]:
        """Loads most recent session context."""
        last_session_id = self.memory_engine.get_kv("last_session_id")
        if not last_session_id:
            return {}
            
        results = self.memory_engine.recall(
            query=str(last_session_id),
            n_results=1,
            memory_type="session_context"
        )
        
        if results:
            import ast
            try:
                # Content is stringified dict
                context = ast.literal_eval(results[0]["content"])
                
                # Restore state
                self.session_id = context.get("session_id", str(uuid.uuid4()))
                self.active_task = context.get("active_task", "")
                self.open_files = context.get("open_files", [])
                self.recent_commands = context.get("recent_commands", [])
                # We start a new timer for the restored session
                self.start_time = datetime.now(timezone.utc) 
                
                return context
            except Exception:
                pass
                
        return {}
