"""Adaptive Model Router — smart model selection based on task complexity.

Design:
- Analyzes task complexity: input length, tool chain depth, risk level
- Simple tasks → small model (fast, low resource)
- Complex tasks → large model (accurate, slower)
- User override: aios --force-model=13b "query"
- Benchmark data stored locally in SQLite
- Improves over weeks of use (learns from user feedback)
- NO cloud dependency — all benchmark data stays local
"""

import os
import json
import time
import sqlite3
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Available Models ──────────────────────────────────────────────

@dataclass
class ModelSpec:
    """Specification for an AI model."""
    id: str
    name: str
    size_params: str          # e.g., "1.1B", "7B", "13B", "70B"
    context_window: int       # max tokens
    speed_tokens_per_sec: int # approximate
    quality_score: float      # 0.0-1.0 (relative quality)
    memory_gb: float          # approximate VRAM needed
    is_local: bool            # True = runs locally, False = cloud
    endpoint: str = ""        # URL or local path

# Default model registry
AVAILABLE_MODELS = [
    ModelSpec(
        id="tiny", name="TinyLLaMA-1.1B", size_params="1.1B",
        context_window=2048, speed_tokens_per_sec=100,
        quality_score=0.30, memory_gb=0.8, is_local=True,
        endpoint="~/.aios/models/tinyllama.gguf"
    ),
    ModelSpec(
        id="small", name="Phi-3-Mini-3.8B", size_params="3.8B",
        context_window=4096, speed_tokens_per_sec=50,
        quality_score=0.50, memory_gb=2.0, is_local=True,
        endpoint="~/.aios/models/phi3-mini.gguf"
    ),
    ModelSpec(
        id="medium", name="Llama-3-8B", size_params="8B",
        context_window=8192, speed_tokens_per_sec=30,
        quality_score=0.65, memory_gb=4.5, is_local=True,
        endpoint="~/.aios/models/llama3-8b.gguf"
    ),
    ModelSpec(
        id="large", name="Llama-3-70B", size_params="70B",
        context_window=8192, speed_tokens_per_sec=5,
        quality_score=0.85, memory_gb=40.0, is_local=True,
        endpoint="~/.aios/models/llama3-70b.gguf"
    ),
    ModelSpec(
        id="cloud-small", name="gpt-4o-mini", size_params="cloud",
        context_window=128000, speed_tokens_per_sec=200,
        quality_score=0.55, memory_gb=0.0, is_local=False,
        endpoint="https://api.openai.com/v1"
    ),
    ModelSpec(
        id="cloud-large", name="claude-sonnet-4", size_params="cloud",
        context_window=200000, speed_tokens_per_sec=100,
        quality_score=0.90, memory_gb=0.0, is_local=False,
        endpoint="https://api.anthropic.com/v1"
    ),
]


@dataclass
class TaskAnalysis:
    """Analysis of task complexity."""
    input_length: int = 0
    estimated_tool_chain_depth: int = 1
    risk_level: str = "low"    # low, medium, high
    requires_reasoning: bool = False
    requires_creativity: bool = False
    has_code: bool = False
    has_math: bool = False
    complexity_score: float = 0.0  # 0.0-1.0

    @property
    def model_tier(self) -> str:
        """Map complexity to model tier."""
        if self.complexity_score < 0.3:
            return "tiny"
        elif self.complexity_score < 0.5:
            return "small"
        elif self.complexity_score < 0.7:
            return "medium"
        else:
            return "large"


@dataclass
class BenchmarkEntry:
    """Record of model performance on a task."""
    timestamp: str = ""
    task_type: str = ""
    model_id: str = ""
    complexity_score: float = 0.0
    latency_ms: float = 0.0
    quality_rating: float = 0.0   # user feedback 0-1
    was_adequate: bool = True
    tokens_used: int = 0


class AdaptiveModelRouter:
    """Routes tasks to the best model based on complexity and benchmarks."""

    def __init__(self, db_path: str = "~/.aios/model_router.db"):
        self.db_path = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()
        self._models: Dict[str, ModelSpec] = {m.id: m for m in AVAILABLE_MODELS}
        self._force_model: Optional[str] = None
        self._benchmark_cache: Dict[str, BenchmarkEntry] = {}

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS benchmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    task_type TEXT,
                    model_id TEXT,
                    complexity_score REAL,
                    latency_ms REAL,
                    quality_rating REAL,
                    was_adequate INTEGER,
                    tokens_used INTEGER
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_bm_model
                ON benchmarks (model_id, task_type)
            """)

    def force_model(self, model_id: str) -> None:
        """Force all tasks to use a specific model (user override)."""
        if model_id in self._models:
            self._force_model = model_id
            logger.info(f"Model forced to: {model_id}")
        else:
            logger.warning(f"Unknown model forced: {model_id}")

    def unforce_model(self) -> None:
        """Remove model forcing."""
        self._force_model = None

    def analyze_task(self, user_input: str, context: Dict = None) -> TaskAnalysis:
        """Analyze task complexity to determine best model tier."""
        analysis = TaskAnalysis(input_length=len(user_input))
        lower = user_input.lower()

        # Tool chain depth estimation
        if any(kw in lower for kw in ["then", "after that", "next", "finally"]):
            analysis.estimated_tool_chain_depth = 3
        elif any(kw in lower for kw in ["and also", "plus", "additionally"]):
            analysis.estimated_tool_chain_depth = 2

        # Risk level
        if any(kw in lower for kw in ["delete", "remove", "kill", "destroy", "format"]):
            analysis.risk_level = "high"
        elif any(kw in lower for kw in ["write", "modify", "change", "update"]):
            analysis.risk_level = "medium"

        # Task characteristics
        analysis.requires_reasoning = any(
            kw in lower for kw in ["why", "how", "analyze", "explain", "compare", "evaluate"]
        )
        analysis.requires_creativity = any(
            kw in lower for kw in ["create", "design", "write", "generate", "compose"]
        )
        analysis.has_code = any(kw in lower for kw in ["code", "function", "script", "python", "def ", "class "])
        analysis.has_math = any(kw in lower for kw in ["calculate", "sum", "average", "percent", "formula"])

        # Complexity scoring (0.0-1.0)
        score = 0.0

        # Input length factor (longer = more complex, but capped)
        score += min(0.2, analysis.input_length / 2000.0)

        # Tool chain depth
        score += min(0.2, analysis.estimated_tool_chain_depth * 0.07)

        # Risk level
        risk_scores = {"low": 0.0, "medium": 0.1, "high": 0.15}
        score += risk_scores.get(analysis.risk_level, 0.0)

        # Task characteristics
        if analysis.requires_reasoning:
            score += 0.15
        if analysis.requires_creativity:
            score += 0.10
        if analysis.has_code:
            score += 0.15
        if analysis.has_math:
            score += 0.10

        analysis.complexity_score = min(1.0, max(0.0, score))
        return analysis

    def select_model(self, user_input: str, context: Dict = None) -> Tuple[ModelSpec, TaskAnalysis]:
        """Select the best model for the given task. Returns (model, analysis)."""
        # Force override
        if self._force_model:
            model = self._models.get(self._force_model, self._models["medium"])
            return model, self.analyze_task(user_input, context)

        analysis = self.analyze_task(user_input, context)

        # Get historical benchmark data
        preferred_model = self._get_preferred_model(analysis)

        # Check if preferred model is available
        if preferred_model.id in self._models:
            return preferred_model, analysis

        # Fallback to medium
        return self._models["medium"], analysis

    def _get_preferred_model(self, analysis: TaskAnalysis) -> ModelSpec:
        """Get the best model based on complexity and historical benchmarks."""
        tier = analysis.model_tier
        task_type = self._classify_task_type(analysis)

        # Check benchmarks for this task type
        best_model_id = self._query_best_model(task_type, analysis.complexity_score)

        if best_model_id and best_model_id in self._models:
            return self._models[best_model_id]

        # Default mapping by tier
        tier_models = {
            "tiny": "tiny",
            "small": "small",
            "medium": "medium",
            "large": "large",
        }
        model_id = tier_models.get(tier, "medium")
        return self._models[model_id]

    def _query_best_model(self, task_type: str, complexity: float) -> Optional[str]:
        """Query benchmark DB for best model on this task type."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT model_id, AVG(quality_rating) as avg_quality,
                           AVG(latency_ms) as avg_latency, COUNT(*) as count
                    FROM benchmarks
                    WHERE task_type = ?
                      AND was_adequate = 1
                    GROUP BY model_id
                    ORDER BY avg_quality DESC, avg_latency ASC
                    LIMIT 1
                """, (task_type,))
                row = cursor.fetchone()
                if row and row[3] >= 3:  # Need at least 3 data points
                    return row[0]
        except Exception as e:
            logger.debug(f"Benchmark query failed: {e}")
        return None

    def record_benchmark(self, entry: BenchmarkEntry) -> None:
        """Record model performance data."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO benchmarks (timestamp, task_type, model_id,
                    complexity_score, latency_ms, quality_rating, was_adequate, tokens_used)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (entry.timestamp, entry.task_type, entry.model_id,
                  entry.complexity_score, entry.latency_ms,
                  entry.quality_rating, int(entry.was_adequate),
                  entry.tokens_used))

    def get_benchmark_stats(self, model_id: str = None) -> List[Dict[str, Any]]:
        """Get benchmark statistics for models."""
        with sqlite3.connect(self.db_path) as conn:
            if model_id:
                cursor = conn.execute("""
                    SELECT model_id, task_type, AVG(quality_rating) as avg_quality,
                           AVG(latency_ms) as avg_latency, COUNT(*) as samples
                    FROM benchmarks
                    WHERE model_id = ?
                    GROUP BY model_id, task_type
                    ORDER BY task_type
                """, (model_id,))
            else:
                cursor = conn.execute("""
                    SELECT model_id, task_type, AVG(quality_rating) as avg_quality,
                           AVG(latency_ms) as avg_latency, COUNT(*) as samples
                    FROM benchmarks
                    GROUP BY model_id, task_type
                    ORDER BY model_id, task_type
                """)
            return [
                {
                    "model_id": row[0],
                    "task_type": row[1],
                    "avg_quality": round(row[2], 3) if row[2] else 0,
                    "avg_latency_ms": round(row[3], 1) if row[3] else 0,
                    "samples": row[4],
                }
                for row in cursor
            ]

    def get_available_models(self) -> List[ModelSpec]:
        """List all available models."""
        return list(self._models.values())

    def _classify_task_type(self, analysis: TaskAnalysis) -> str:
        """Classify task into a type for benchmarking."""
        if analysis.has_code:
            return "code"
        if analysis.has_math:
            return "math"
        if analysis.requires_reasoning:
            return "reasoning"
        if analysis.requires_creativity:
            return "creative"
        if analysis.risk_level == "high":
            return "high_risk"
        return "general"


# ── Integration with Shell ────────────────────────────────────────

def create_router(db_path: str = None) -> AdaptiveModelRouter:
    """Create a model router with default settings."""
    if db_path:
        return AdaptiveModelRouter(db_path=db_path)
    return AdaptiveModelRouter()
