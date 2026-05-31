import os
import json
import time
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

@dataclass
class ReportEntry:
    timestamp: str = ""
    task_goal: str = ""
    success: bool = False
    result: str = ""
    error: str = ""
    duration_ms: int = 0

class AutoReporter:
    """Generates daily/weekly reports of AIOS activity."""

    def __init__(self, db_path: str = "~/.aios/reports.db"):
        self.db_path = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS report_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    task_goal TEXT,
                    success INTEGER,
                    result TEXT,
                    error TEXT,
                    duration_ms INTEGER
                )
            """)

    def log_task(self, goal: str, success: bool, result: str = "",
                 error: str = "", duration_ms: int = 0) -> None:
        """Log a completed task for reporting."""
        import sqlite3
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO report_entries (timestamp, task_goal, success, result, error, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (now, goal, int(success), result[:500], error[:500], duration_ms))

    def _get_entries(self, since: datetime) -> List[ReportEntry]:
        import sqlite3
        since_str = since.isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM report_entries
                WHERE timestamp >= ?
                ORDER BY timestamp ASC
            """, (since_str,))
            return [ReportEntry(**{k: v for k, v in dict(r).items() if k != 'id'}) for r in cursor]

    def daily_report(self) -> Dict[str, Any]:
        """Generate report for the last 24 hours."""
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        return self._build_report(since, "daily")

    def weekly_report(self) -> Dict[str, Any]:
        """Generate report for the last 7 days."""
        since = datetime.now(timezone.utc) - timedelta(days=7)
        return self._build_report(since, "weekly")

    def _build_report(self, since: datetime, period: str) -> Dict[str, Any]:
        entries = self._get_entries(since)

        total = len(entries)
        success_count = sum(1 for e in entries if e.success)
        failed_count = total - success_count
        avg_duration = (
            sum(e.duration_ms for e in entries) / total
            if total > 0 else 0
        )

        failed_tasks = [
            {"goal": e.task_goal, "error": e.error}
            for e in entries if not e.success
        ]

        top_tasks = {}
        for e in entries:
            top_tasks[e.task_goal] = top_tasks.get(e.task_goal, 0) + 1
        top_tasks_sorted = sorted(top_tasks.items(), key=lambda x: -x[1])[:10]

        return {
            "period": period,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_tasks": total,
                "successful": success_count,
                "failed": failed_count,
                "success_rate": round(success_count / total * 100, 1) if total > 0 else 0,
                "avg_duration_ms": round(avg_duration, 1),
            },
            "top_tasks": [{"goal": g, "count": c} for g, c in top_tasks_sorted],
            "failed_tasks": failed_tasks,
        }

    def format_report(self, report: Dict[str, Any]) -> str:
        """Format report as human-readable text."""
        s = report["summary"]
        lines = [
            f"AIOS {report['period'].capitalize()} Report",
            f"Generated: {report['generated_at'][:19]}",
            "",
            f"Total Tasks: {s['total_tasks']}",
            f"Successful:  {s['successful']}",
            f"Failed:      {s['failed']}",
            f"Success Rate: {s['success_rate']}%",
            f"Avg Duration: {s['avg_duration_ms']}ms",
            "",
        ]

        if report["top_tasks"]:
            lines.append("Most Common Tasks:")
            for t in report["top_tasks"]:
                lines.append(f"  - {t['goal']} ({t['count']}x)")
            lines.append("")

        if report["failed_tasks"]:
            lines.append("Failed Tasks:")
            for t in report["failed_tasks"]:
                lines.append(f"  - {t['goal']}: {t['error']}")
            lines.append("")

        lines.append("--- End of Report ---")
        return "\n".join(lines)

    def clear_old_entries(self, days: int = 30) -> int:
        """Delete entries older than N days."""
        import sqlite3
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM report_entries WHERE timestamp < ?", (cutoff,))
            deleted = cursor.rowcount
            if deleted > 0:
                logger.info(f"Cleared {deleted} old report entries")
            return deleted
