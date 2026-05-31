import os
import sqlite3
from enum import Enum
from dataclasses import dataclass

class Permission(Enum):
    FILE_READ = "FILE_READ"
    FILE_WRITE = "FILE_WRITE"
    PROCESS_KILL = "PROCESS_KILL"
    NETWORK_ACCESS = "NETWORK_ACCESS"
    SYSTEM_MODIFY = "SYSTEM_MODIFY"

class PermissionDenied(Exception):
    pass

class PermissionManager:
    """Capability-based permission system for tools."""
    
    def __init__(self, db_path: str = "~/.aios/permissions.db"):
        self.db_path = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()
        
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS tool_permissions (
                    tool_name TEXT,
                    permission TEXT,
                    PRIMARY KEY (tool_name, permission)
                )
            ''')
            
    def grant(self, tool_name: str, permission: Permission) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                'INSERT OR IGNORE INTO tool_permissions (tool_name, permission) VALUES (?, ?)',
                (tool_name, permission.value)
            )
            
    def revoke(self, tool_name: str, permission: Permission) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                'DELETE FROM tool_permissions WHERE tool_name = ? AND permission = ?',
                (tool_name, permission.value)
            )
            
    def check(self, tool_name: str, permission: Permission) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                'SELECT 1 FROM tool_permissions WHERE tool_name = ? AND permission = ?',
                (tool_name, permission.value)
            )
            return cursor.fetchone() is not None
            
    def require(self, tool_name: str, permission: Permission) -> None:
        if not self.check(tool_name, permission):
            raise PermissionDenied(f"Tool '{tool_name}' requires permission {permission.value} but it is not granted.")
