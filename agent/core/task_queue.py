import os
import sqlite3
import json
import time
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

class TaskStatus:
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    RETRY = "retry"
    CANCELLED = "cancelled"

class TaskPriority:
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class Task:
    id: Optional[int] = None
    goal: str = ""
    priority: str = "medium"
    status: str = "pending"
    created_at: str = ""
    updated_at: str = ""
    retry_count: int = 0
    max_retries: int = 3
    result: Optional[str] = None
    error: Optional[str] = None
    context: Optional[str] = None

class TaskQueue:
    """Persistent task queue with scheduling capabilities."""

    def __init__(self, db_path: str = "~/.aios/tasks.db"):
        self.db_path = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal TEXT NOT NULL,
                    priority TEXT DEFAULT 'medium',
                    status TEXT DEFAULT 'pending',
                    created_at TEXT,
                    updated_at TEXT,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    result TEXT,
                    error TEXT,
                    context TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_status
                ON tasks (status, priority)
            """)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def add(self, goal: str, priority: str = "medium", context: Dict = None,
            max_retries: int = 3) -> int:
        """Add a new task to the queue. Returns task ID."""
        now = self._now()
        ctx = json.dumps(context) if context else None

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO tasks (goal, priority, status, created_at, updated_at, retry_count, max_retries, context) VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
                (goal, priority, TaskStatus.PENDING, now, now, max_retries, ctx))
            task_id = cursor.lastrowid
            logger.info(f"Task added: #{task_id} [{priority}] {goal}")
            return task_id

    def get_next(self) -> Optional[Task]:
        """Get the highest priority pending task."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM tasks WHERE status IN (?, ?) ORDER BY priority ASC, created_at ASC LIMIT 1",
                (TaskStatus.PENDING, TaskStatus.RETRY))

            row = cursor.fetchone()
            if row:
                return Task(**dict(row))
            return None

    def mark_running(self, task_id: int) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                (TaskStatus.RUNNING, self._now(), task_id))

    def mark_done(self, task_id: int, result: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE tasks SET status = ?, result = ?, updated_at = ? WHERE id = ?",
                (TaskStatus.DONE, result, self._now(), task_id))

    def mark_failed(self, task_id: int, error: str) -> None:
        """Mark task as failed. Auto-requeue if retries remaining."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT retry_count, max_retries FROM tasks WHERE id = ?",
                              (task_id,)).fetchone()
            if row and row["retry_count"] < row["max_retries"]:
                conn.execute(
                    "UPDATE tasks SET status = ?, retry_count = retry_count + 1, error = ?, updated_at = ? WHERE id = ?",
                    (TaskStatus.RETRY, error, self._now(), task_id))
                logger.info(f"Task #{task_id} queued for retry")
            else:
                conn.execute(
                    "UPDATE tasks SET status = ?, error = ?, updated_at = ? WHERE id = ?",
                    (TaskStatus.FAILED, error, self._now(), task_id))
                logger.warning(f"Task #{task_id} permanently failed")

    def cancel(self, task_id: int) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                (TaskStatus.CANCELLED, self._now(), task_id))

    def list_tasks(self, status: Optional[str] = None, limit: int = 50) -> List[Task]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if status:
                cursor = conn.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit))
            else:
                cursor = conn.execute(
                    "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
                    (limit,))
            return [Task(**dict(r)) for r in cursor]

    def stats(self) -> Dict[str, int]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT status, COUNT(*) as count FROM tasks GROUP BY status")
            return {row[0]: row[1] for row in cursor}
