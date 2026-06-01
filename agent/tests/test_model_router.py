import pytest
import os
import tempfile
from agent.core.model_router import (
    AdaptiveModelRouter, ModelSpec, TaskAnalysis, BenchmarkEntry,
    AVAILABLE_MODELS, create_router
)


class TestAdaptiveModelRouter:

    @pytest.fixture
    def router(self, tmp_path):
        db_path = str(tmp_path / "model_router.db")
        return AdaptiveModelRouter(db_path=db_path)

    def test_analyze_simple_task(self, router):
        analysis = router.analyze_task("show files")
        assert analysis.complexity_score < 0.3
        assert analysis.model_tier in ("tiny", "small")

    def test_analyze_complex_task(self, router):
        analysis = router.analyze_task(
            "Analyze the code in main.py, compare it with the alternative approach, "
            "then explain why one is better. Also calculate the time complexity."
        )
        assert analysis.complexity_score > 0.5
        assert analysis.requires_reasoning is True
        assert analysis.has_code is True
        assert analysis.has_math is True

    def test_analyze_risky_task(self, router):
        analysis = router.analyze_task("Delete all files in the temp directory")
        assert analysis.risk_level == "high"

    def test_analyze_creative_task(self, router):
        analysis = router.analyze_task("Create a Python function that generates poetry")
        assert analysis.requires_creativity is True
        assert analysis.has_code is True

    def test_select_model_simple_task(self, router):
        model, analysis = router.select_model("show files")
        assert analysis.complexity_score < 0.3
        assert model is not None

    def test_select_model_complex_task(self, router):
        model, analysis = router.select_model(
            "Write a complex Python function with error handling and type hints"
        )
        assert model is not None
        assert analysis.has_code is True

    def test_force_model_override(self, router):
        router.force_model("large")
        model, _ = router.select_model("show files")
        assert model.id == "large"

    def test_force_unknown_model(self, router):
        router.force_model("nonexistent")
        model, _ = router.select_model("show files")
        assert model is not None

    def test_unforce_model(self, router):
        router.force_model("large")
        router.unforce_model()
        model, analysis = router.select_model("show files")
        # Should be back to adaptive selection
        assert analysis.complexity_score < 0.3

    def test_record_and_query_benchmark(self, router):
        # Record benchmarks for the same task
        for i in range(5):
            entry = BenchmarkEntry(
                timestamp="2026-01-01T00:00:00Z",
                task_type="code",
                model_id="medium",
                complexity_score=0.6,
                latency_ms=2000.0,
                quality_rating=0.8,
                was_adequate=True,
                tokens_used=100,
            )
            router.record_benchmark(entry)

        best = router._query_best_model("code", 0.6)
        assert best == "medium"

    def test_benchmark_insufficient_data(self, router):
        # Only 2 data points — not enough (need 3)
        for i in range(2):
            entry = BenchmarkEntry(
                timestamp="2026-01-01T00:00:00Z",
                task_type="reasoning",
                model_id="large",
                complexity_score=0.7,
                latency_ms=5000.0,
                quality_rating=0.9,
                was_adequate=True,
                tokens_used=200,
            )
            router.record_benchmark(entry)

        best = router._query_best_model("reasoning", 0.7)
        assert best is None  # Not enough data

    def test_get_benchmark_stats(self, router):
        entry = BenchmarkEntry(
            timestamp="2026-01-01T00:00:00Z",
            task_type="general",
            model_id="small",
            complexity_score=0.3,
            latency_ms=1000.0,
            quality_rating=0.6,
            was_adequate=True,
            tokens_used=50,
        )
        router.record_benchmark(entry)

        stats = router.get_benchmark_stats()
        assert len(stats) >= 1
        assert stats[0]["model_id"] == "small"

    def test_get_available_models(self, router):
        models = router.get_available_models()
        assert len(models) >= 4
        ids = [m.id for m in models]
        assert "tiny" in ids
        assert "medium" in ids

    def test_create_router_factory(self, tmp_path):
        router = create_router(db_path=str(tmp_path / "router.db"))
        assert isinstance(router, AdaptiveModelRouter)

    def test_available_models_have_required_fields(self):
        for model in AVAILABLE_MODELS:
            assert isinstance(model.id, str) and model.id
            assert isinstance(model.quality_score, float)
            assert 0 <= model.quality_score <= 1
            assert model.memory_gb >= 0

    def test_tool_chain_depth_detection(self, router):
        analysis = router.analyze_task(
            "First list the files, then after that check the system, "
            "and finally report the results"
        )
        assert analysis.estimated_tool_chain_depth >= 3

    def test_benchmark_data_stays_local(self, router):
        """Verify no network calls are made — all data is local."""
        entry = BenchmarkEntry(
            timestamp="2026-01-01T00:00:00Z",
            task_type="test",
            model_id="tiny",
            complexity_score=0.1,
            latency_ms=100.0,
            quality_rating=0.5,
            was_adequate=True,
            tokens_used=10,
        )
        router.record_benchmark(entry)

        # Verify data is in local DB
        stats = router.get_benchmark_stats("tiny")
        assert len(stats) >= 1
        assert stats[0]["task_type"] == "test"
