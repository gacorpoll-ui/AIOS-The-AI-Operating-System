"""Metacognition Engine — AIOS self-assessment and black box recorder."""

import os
import json
import time
import sqlite3
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


# ── Lightweight YAML parser (no dependency needed) ──────────────────

def _parse_yaml(path: str) -> Dict[str, Any]:
    """Minimal YAML parser for our flat config format."""
    config: Dict[str, Any] = {}
    current_section = None

    with open(path, "r") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            # Section header (no leading space, ends with colon, no value)
            if not raw_line.startswith(" ") and ":" in line and not any("=" in line for line in [raw_line]):
                key, _, rest = line.partition(":")
                rest = rest.strip()
                if not rest:
                    current_section = key
                    config[current_section] = {}
                    continue
                # inline value
                val = _yaml_val(rest)
                config[key] = val
                continue

            # Key-value inside a section
            if current_section and ":" in line:
                k, _, v = line.partition(":")
                config[current_section][k.strip()] = _yaml_val(v)

    return config


def _yaml_val(s: str) -> Any:
    s = s.strip()
    if s.startswith("#"):
        return None
    # Remove inline comments
    comment_idx = s.find(" #")
    if comment_idx > 0:
        s = s[:comment_idx].strip()
    if s in ("true", "True"):
        return True
    if s in ("false", "False"):
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s.strip('"').strip("'")


# ── Dataclasses ─────────────────────────────────────────────────────

@dataclass
class Assessment:
    id: Optional[int] = None
    timestamp: str = ""
    task_goal: str = ""
    confidence: float = 0.0
    above_threshold: bool = False
    threshold: float = 0.0
    breakdown: str = ""   # JSON string of sub-scores
    result_summary: str = ""
    duration_ms: int = 0


# ── Black Box Recorder ─────────────────────────────────────────────

class BlackBoxRecorder:
    """Append-only log of ALL assessments (like a flight data recorder)."""

    def __init__(self, db_path: str = "~/.aios/blackbox.db",
                 max_entries: int = 10000, auto_rotate: bool = True):
        self.db_path = os.path.expanduser(db_path)
        self.max_entries = max_entries
        self.auto_rotate = auto_rotate
        self._persistent_conn = None  # For :memory: mode
        if self.db_path == ":memory:":
            self._persistent_conn = sqlite3.connect(":memory:")
            self._init_db_with_conn(self._persistent_conn)
        else:
            dir_path = os.path.dirname(self.db_path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            self._init_db_with_conn(conn)

    def _init_db_with_conn(self, conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS black_box (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                task_goal TEXT,
                confidence REAL,
                above_threshold INTEGER,
                threshold REAL,
                breakdown TEXT,
                result_summary TEXT,
                duration_ms INTEGER
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bb_ts ON black_box(timestamp)")
        conn.commit()

    def _conn(self):
        """Get connection — persistent for :memory:, fresh for file."""
        if self._persistent_conn:
            return self._persistent_conn
        return sqlite3.connect(self.db_path)

    def record(self, assessment: Assessment) -> None:
        conn = self._conn()
        ctx = conn if self._persistent_conn else conn
        with ctx if not self._persistent_conn else conn:
            conn.execute("""
                INSERT INTO black_box (timestamp, task_goal, confidence, above_threshold,
                                       threshold, breakdown, result_summary, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (assessment.timestamp, assessment.task_goal, assessment.confidence,
                  int(assessment.above_threshold), assessment.threshold,
                  assessment.breakdown, assessment.result_summary, assessment.duration_ms))
            conn.commit()

            if self.auto_rotate and not self._persistent_conn:
                count = conn.execute("SELECT COUNT(*) FROM black_box").fetchone()[0]
                if count > self.max_entries:
                    oldest = count - self.max_entries
                    conn.execute(
                        "DELETE FROM black_box WHERE id IN (SELECT id FROM black_box ORDER BY id ASC LIMIT ?)",
                        (oldest,))
                    conn.commit()
                    logger.info(f"Black box rotated: removed {oldest} old entries")

    def get_recent(self, n: int = 50) -> List[Assessment]:
        conn = self._conn()
        cursor = conn.execute(
            "SELECT * FROM black_box ORDER BY id DESC LIMIT ?", (n,))
        results = []
        for row in cursor:
            d = dict(zip([c[0] for c in cursor.description], row))
            d["above_threshold"] = bool(d["above_threshold"])
            results.append(Assessment(**d))
        return results[::-1]

    def stats(self, last_n: int = 100) -> Dict[str, Any]:
        conn = self._conn()
        cursor = conn.execute("""
            SELECT COUNT(*) as total,
                   AVG(confidence) as avg_conf,
                   MIN(confidence) as min_conf,
                   MAX(confidence) as max_conf,
                   AVG(duration_ms) as avg_ms
            FROM black_box
            WHERE id >= (SELECT MAX(id) - ? FROM black_box)
        """, (last_n,))
        row = cursor.fetchone()
        return {
            "total": row[0],
            "avg_confidence": round(row[1] or 0, 3),
            "min_confidence": round(row[2] or 0, 3),
            "max_confidence": round(row[3] or 0, 3),
            "avg_assessment_ms": round(row[4] or 0, 1),
        }


# ── Metacognition Engine ───────────────────────────────────────────

class MetacogEngine:
    """Self-assessment engine. Evaluates confidence in <2 seconds."""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "config", "metacog.yaml")

        self.config = _parse_yaml(config_path) if os.path.exists(config_path) else {}
        self.threshold = self.config.get("threshold", 0.65)
        weights_cfg = self.config.get("weights", {})
        self.weights = {
            "tool_success": float(weights_cfg.get("tool_success", 0.30)),
            "llm_certainty": float(weights_cfg.get("llm_certainty", 0.25)),
            "context_relevance": float(weights_cfg.get("context_relevance", 0.25)),
            "error_signals": float(weights_cfg.get("error_signals", 0.20)),
        }

        bb_cfg = self.config.get("black_box", {})
        bb_db = bb_cfg.get("db_path", "~/.aios/blackbox.db")
        self.black_box = BlackBoxRecorder(
            db_path=str(bb_db),
            max_entries=int(bb_cfg.get("max_entries", 10000)),
            auto_rotate=bool(bb_cfg.get("auto_rotate", True)),
        ) if bb_cfg.get("enabled", True) else None

    def assess(self, goal: str, tool_results: List[Dict] = None,
               llm_output: str = "", errors: List[str] = None) -> Assessment:
        """Run self-assessment. Always logged to black box. Always < 2s."""
        start = time.time()

        if tool_results is None:
            tool_results = []
        if errors is None:
            errors = []

        # 1. Tool success score
        if tool_results:
            success_count = sum(1 for t in tool_results if t.get("success", False))
            tool_score = success_count / len(tool_results)
        else:
            tool_score = 0.5  # neutral — no tools used

        # 2. LLM certainty (heuristic: empty output = low, short = uncertain)
        if not llm_output:
            llm_score = 0.2
        elif len(llm_output) < 10:
            llm_score = 0.4
        elif any(kw in llm_output.lower() for kw in ["don't know", "cannot", "unable", "not sure", "uncertain"]):
            llm_score = 0.3
        else:
            llm_score = 0.85

        # 3. Context relevance (heuristic: longer goal = more specific = higher)
        if len(goal) > 5:
            context_score = min(1.0, len(goal) / 50.0)
        else:
            context_score = 0.3

        # 4. Error signals
        if errors:
            error_score = max(0.0, 1.0 - (len(errors) * 0.25))
        else:
            error_score = 1.0

        # Weighted average
        w = self.weights
        confidence = (
            w["tool_success"] * tool_score +
            w["llm_certainty"] * llm_score +
            w["context_relevance"] * context_score +
            w["error_signals"] * error_score
        )
        confidence = round(min(1.0, max(0.0, confidence)), 3)

        duration_ms = int((time.time() - start) * 1000)

        breakdown = json.dumps({
            "tool_success": round(tool_score, 3),
            "llm_certainty": round(llm_score, 3),
            "context_relevance": round(context_score, 3),
            "error_signals": round(error_score, 3),
        })

        assessment = Assessment(
            timestamp=datetime.now(timezone.utc).isoformat(),
            task_goal=goal,
            confidence=confidence,
            above_threshold=confidence >= self.threshold,
            threshold=self.threshold,
            breakdown=breakdown,
            result_summary=llm_output[:200] if llm_output else "",
            duration_ms=duration_ms,
        )

        # ALWAYS log to black box
        if self.black_box:
            self.black_box.record(assessment)

        logger.info(f"Assessment [{goal[:40]}]: confidence={confidence}, "
                     f"duration={duration_ms}ms, above_threshold={assessment.above_threshold}")
        return assessment

    def should_warn(self, assessment: Assessment) -> bool:
        """Return True if response should include uncertainty warning."""
        warn_cfg = self.config.get("low_confidence_behavior", {})
        if not warn_cfg.get("warn_user", True):
            return False
        return not assessment.above_threshold

    def warning_message(self, assessment: Assessment) -> str:
        warn_cfg = self.config.get("low_confidence_behavior", {})
        if assessment.above_threshold:
            return ""
        msg = f"\n[AIOS] Confidence: {assessment.confidence:.0%} (threshold: {assessment.threshold:.0%})"
        if warn_cfg.get("suggest_clarification", True):
            msg += " — consider rephrasing your request for better results."
        return msg
