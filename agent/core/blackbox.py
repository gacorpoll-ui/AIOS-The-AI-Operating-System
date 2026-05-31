"""Tamper-Proof Black Box Recorder — separate, append-only, hashed, auto-rotated.

Design:
- Separate SQLite DB file from main AIOS DB
- INSERT-only enforcement: no DELETE/UPDATE on black_box table
- SHA256 hash chain: each row's hash depends on previous row (tamper-evident)
- Monthly auto-rotation: old DBs compressed to .gz and kept forever
"""

import os
import gzip
import json
import sqlite3
import hashlib
import shutil
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


class TamperProofBlackBox:
    """Append-only, hashed, auto-rotating black box recorder."""

    def __init__(self, db_dir: str = "~/.aios/blackbox",
                 hash_algo: str = "sha256"):
        self.db_dir = os.path.expanduser(db_dir)
        os.makedirs(self.db_dir, exist_ok=True)
        self.hash_algo = hash_algo
        self._current_db = self._get_current_db_path()
        self._ensure_current_db()
        self._rotate_if_needed()

    def _get_current_db_path(self) -> str:
        """Get path for current month's black box DB."""
        now = datetime.now(timezone.utc)
        return os.path.join(self.db_dir, f"blackbox_{now.strftime('%Y_%m')}.db")

    def _ensure_current_db(self) -> None:
        """Create table if not exists. Enforce INSERT-only via trigger."""
        with sqlite3.connect(self._current_db) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    event_type TEXT,
                    data_json TEXT,
                    prev_hash TEXT,
                    self_hash TEXT
                )
            """)
            # INSERT-only enforcement: prevent DELETE and UPDATE
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS prevent_delete
                BEFORE DELETE ON events
                BEGIN
                    SELECT RAISE(ABORT, 'BLACKBOX VIOLATION: DELETE not allowed on black box recorder');
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS prevent_update
                BEFORE UPDATE ON events
                BEGIN
                    SELECT RAISE(ABORT, 'BLACKBOX VIOLATION: UPDATE not allowed on black box recorder');
                END
            """)
            conn.commit()

    def _get_last_hash(self) -> str:
        """Get the hash of the last event (for chain linking)."""
        with sqlite3.connect(self._current_db) as conn:
            cursor = conn.execute(
                "SELECT self_hash FROM events ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            return row[0] if row else "genesis"

    def _compute_hash(self, timestamp: str, event_type: str,
                      data_json: str, prev_hash: str) -> str:
        """Compute SHA256 hash for this event."""
        content = f"{timestamp}|{event_type}|{data_json}|{prev_hash}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def insert(self, event_type: str, data: Dict[str, Any]) -> str:
        """Insert event. Returns self_hash. INSERT-ONLY enforced by trigger."""
        timestamp = datetime.now(timezone.utc).isoformat()
        data_json = json.dumps(data, sort_keys=True)
        prev_hash = self._get_last_hash()
        self_hash = self._compute_hash(timestamp, event_type, data_json, prev_hash)

        with sqlite3.connect(self._current_db) as conn:
            conn.execute("""
                INSERT INTO events (timestamp, event_type, data_json, prev_hash, self_hash)
                VALUES (?, ?, ?, ?, ?)
            """, (timestamp, event_type, data_json, prev_hash, self_hash))
            conn.commit()

        logger.debug(f"BlackBox insert [{event_type}]: hash={self_hash[:16]}...")
        return self_hash

    def get_chain(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent events with their hashes."""
        with sqlite3.connect(self._current_db) as conn:
            cursor = conn.execute(
                "SELECT id, timestamp, event_type, data_json, prev_hash, self_hash "
                "FROM events ORDER BY id DESC LIMIT ?",
                (limit,))
            results = []
            for row in cursor:
                results.append({
                    "id": row[0],
                    "timestamp": row[1],
                    "event_type": row[2],
                    "data": json.loads(row[3]) if row[3] else {},
                    "prev_hash": row[4],
                    "self_hash": row[5],
                })
            return results[::-1]  # chronological

    def verify_integrity(self) -> Dict[str, Any]:
        """Verify the entire hash chain. Returns integrity report."""
        with sqlite3.connect(self._current_db) as conn:
            cursor = conn.execute(
                "SELECT id, timestamp, event_type, data_json, prev_hash, self_hash "
                "FROM events ORDER BY id ASC")

            prev_hash = "genesis"
            total = 0
            tampered = []

            for row in cursor:
                row_id, ts, etype, data_json, stored_prev, stored_self = row
                expected_self = self._compute_hash(ts, etype, data_json, prev_hash)

                if stored_self != expected_self:
                    tampered.append(row_id)

                prev_hash = stored_self
                total += 1

            return {
                "total_events": total,
                "tampered_ids": tampered,
                "integrity": "INTACT" if not tampered else f"TAMPERED: {len(tampered)} events",
                "db_file": self._current_db,
            }

    def _rotate_if_needed(self) -> Optional[str]:
        """Rotate if we're in a new month. Compress old DB."""
        current = self._get_current_db_path()
        if current != self._current_db:
            old_db = self._current_db
            self._current_db = current
            self._compress_old_db(old_db)
            self._ensure_current_db()
            logger.info(f"Black box rotated: {old_db} -> {current}")
            return old_db
        return None

    def _compress_old_db(self, db_path: str) -> None:
        """Compress old DB to .gz, keep forever."""
        if os.path.exists(db_path):
            gz_path = db_path + ".gz"
            with open(db_path, "rb") as f_in:
                with gzip.open(gz_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            logger.info(f"Black box archived: {db_path} -> {gz_path}")

    def get_archives(self) -> List[str]:
        """List all archived (compressed) black box files."""
        archives = []
        for f in os.listdir(self.db_dir):
            if f.startswith("blackbox_") and f.endswith(".gz"):
                archives.append(os.path.join(self.db_dir, f))
        return sorted(archives)

    def read_archive(self, gz_path: str) -> List[Dict[str, Any]]:
        """Read events from a compressed archive."""
        with gzip.open(gz_path, "rb") as f:
            tmp_path = gz_path.replace(".gz", ".tmp")
            with open(tmp_path, "wb") as tmp:
                tmp.write(f.read())
        events = []
        try:
            with sqlite3.connect(tmp_path) as conn:
                cursor = conn.execute(
                    "SELECT id, timestamp, event_type, data_json, prev_hash, self_hash "
                    "FROM events ORDER BY id ASC")
                for row in cursor:
                    events.append({
                        "id": row[0],
                        "timestamp": row[1],
                        "event_type": row[2],
                        "data": json.loads(row[3]) if row[3] else {},
                        "prev_hash": row[4],
                        "self_hash": row[5],
                    })
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        return events
