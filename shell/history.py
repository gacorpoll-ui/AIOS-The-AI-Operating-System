import sqlite3
import os
import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

class ShellHistory:
    """Manages command history and semantic search of past interactions."""
    
    def __init__(self, db_path: str = "~/.aios/shell_history.db"):
        self.db_path = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()
        
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    user_input TEXT,
                    interpreted_intent TEXT,
                    tools_called TEXT,
                    success BOOLEAN
                )
            ''')
            
    def add(self, entry: Dict[str, Any]) -> None:
        """Saves a history entry to SQLite."""
        timestamp = entry.get("timestamp", datetime.now(timezone.utc).isoformat())
        user_input = entry.get("user_input", "")
        intent = entry.get("interpreted_intent", "")
        tools = json.dumps(entry.get("tools_called", []))
        success = entry.get("success", True)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO history (timestamp, user_input, interpreted_intent, tools_called, success)
                    VALUES (?, ?, ?, ?, ?)
                ''', (timestamp, user_input, intent, tools, success))
        except Exception as e:
            # We don't want history failures to break the shell
            pass
            
    def get_recent(self, n: int = 20) -> List[Dict[str, Any]]:
        """Retrieves the n most recent history entries."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute('''
                    SELECT * FROM history 
                    ORDER BY id DESC 
                    LIMIT ?
                ''', (n,))
                
                results = []
                for row in cursor:
                    results.append({
                        "id": row["id"],
                        "timestamp": row["timestamp"],
                        "user_input": row["user_input"],
                        "interpreted_intent": row["interpreted_intent"],
                        "tools_called": json.loads(row["tools_called"]),
                        "success": bool(row["success"])
                    })
                return results[::-1] # Return in chronological order
        except Exception:
            return []
            
    def search(self, query: str) -> List[Dict[str, Any]]:
        """Semantic search on past commands (simplified to LIKE match for now)."""
        # In a real implementation, we would use ChromaDB / Vector search here
        # similar to the MemoryEngine implementation.
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                search_term = f"%{query}%"
                cursor = conn.execute('''
                    SELECT * FROM history 
                    WHERE user_input LIKE ? OR interpreted_intent LIKE ?
                    ORDER BY id DESC 
                    LIMIT 10
                ''', (search_term, search_term))
                
                results = []
                for row in cursor:
                    results.append({
                        "id": row["id"],
                        "timestamp": row["timestamp"],
                        "user_input": row["user_input"],
                        "interpreted_intent": row["interpreted_intent"],
                        "tools_called": json.loads(row["tools_called"]),
                        "success": bool(row["success"])
                    })
                return results
        except Exception:
            return []
