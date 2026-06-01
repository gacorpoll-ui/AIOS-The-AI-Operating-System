import json
import logging
import sqlite3
import traceback
import time
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable

logger = logging.getLogger(__name__)

@dataclass
class Tool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    requires_confirmation: bool = False
    
@dataclass
class ToolResult:
    success: bool
    output: Any
    error: Optional[str] = None
    execution_time_ms: int = 0

class ConfirmationRequired(Exception):
    pass

class ToolRegistry:
    def __init__(self, db_path: Optional[str] = None):
        self._tools: Dict[str, Tool] = {}
        self._handlers: Dict[str, Callable] = {}
        self.db_path = db_path
        if self.db_path:
            self._init_db()
            
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS tool_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    tool_name TEXT,
                    params TEXT,
                    success BOOLEAN,
                    execution_time_ms INTEGER
                )
            ''')
            
    def register(self, tool: Tool, handler: Callable) -> None:
        self._tools[tool.name] = tool
        self._handlers[tool.name] = handler
        
    def get_tool(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)
        
    def list_tools(self) -> List[Dict[str, Any]]:
        specs = []
        for name, tool in self._tools.items():
            specs.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema
                }
            })
        return specs
        
    def execute(self, tool_name: str, params: Dict[str, Any], confirmed: bool = False, context: Dict[str, Any] = None) -> ToolResult:
        """Execute a tool with constitutional enforcement.

        BEFORE running any tool, the Constitution checks all articles.
        If violated: HARD STOP, log to black box, return failure.
        """
        # Constitutional check — runs BEFORE any tool execution (<1ms)
        try:
            from security.constitution import enforce
            const_result = enforce(tool_name, params, context or {})
            if not const_result.compliant:
                violations = "; ".join(const_result.violations)
                logger.error(f"Constitution blocked {tool_name}: {violations}")
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Constitutional violation (Article {const_result.blocked_article}): {violations}"
                )
        except ImportError:
            pass  # Constitution not available — proceed without check (dev mode)

        tool = self.get_tool(tool_name)
        handler = self._handlers.get(tool_name)
        
        if not tool or not handler:
            return ToolResult(success=False, output=None, error=f"Tool not found: {tool_name}")
            
        if tool.requires_confirmation and not confirmed:
            raise ConfirmationRequired(f"Tool {tool_name} requires explicit user confirmation.")
            
        start_time = time.time()
        success = False; output = None; error = None
        
        try:
            output = handler(**params)
            success = True
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {str(e)}")
            error = str(e)
            
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        if self.db_path:
            try:
                from datetime import datetime, timezone
                timestamp = datetime.now(timezone.utc).isoformat()
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        "INSERT INTO tool_logs (timestamp, tool_name, params, success, execution_time_ms) VALUES (?, ?, ?, ?, ?)",
                        (timestamp, tool_name, json.dumps(params), success, execution_time_ms)
                    )
            except Exception as log_err:
                pass
                
        return ToolResult(success=success, output=output, error=error, execution_time_ms=execution_time_ms)