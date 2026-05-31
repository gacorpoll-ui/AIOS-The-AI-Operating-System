import pytest
import time
import os
from agent.core.metacog import (
    MetacogEngine, BlackBoxRecorder, Assessment, _parse_yaml
)


class TestMetacogEngine:

    @pytest.fixture
    def engine(self, tmp_path):
        config = tmp_path / "metacog.yaml"
        config.write_text(
            "threshold: 0.40\n"
            "black_box:\n"
            "  enabled: true\n"
            "  max_entries: 100\n"
            "  auto_rotate: true\n"
            "  db_path: " + str(tmp_path / "bb.db") + "\n"
        )
        return MetacogEngine(config_path=str(config))

    def test_assessment_returns_above_threshold(self, engine):
        result = engine.assess("show files", tool_results=[{"success": True}], llm_output="Here are your files")
        assert result.above_threshold is True

    def test_assessment_returns_below_threshold(self, engine):
        result = engine.assess("x", errors=["fail1", "fail2", "fail3", "fail4", "fail5"])
        assert result.confidence < engine.threshold
        assert result.above_threshold is False

    def test_assessment_completes_under_2_seconds(self, engine):
        start = time.time()
        engine.assess("test task", llm_output="result")
        elapsed = time.time() - start
        assert elapsed < 2.0, f"Assessment took {elapsed:.3f}s, must be < 2s"

    def test_all_assessments_logged_to_black_box(self, engine):
        engine.assess("task 1", llm_output="ok")
        engine.assess("task 2", errors=["fail"])
        engine.assess("task 3")

        entries = engine.black_box.get_recent(100)
        assert len(entries) == 3

    def test_black_box_auto_rotate(self, tmp_path):
        config = tmp_path / "metacog.yaml"
        config.write_text(
            "threshold: 0.5\n"
            "black_box:\n"
            "  enabled: true\n"
            "  max_entries: 5\n"
            "  auto_rotate: true\n"
            "  db_path: " + str(tmp_path / "bb2.db") + "\n"
        )
        engine = MetacogEngine(config_path=str(config))

        for i in range(10):
            engine.assess(f"task {i}")

        entries = engine.black_box.get_recent(100)
        assert len(entries) <= 5

    def test_should_warn_below_threshold(self, engine):
        result = engine.assess("x", errors=["fail"] * 5)
        assert engine.should_warn(result) is True

    def test_should_not_warn_above_threshold(self, engine):
        result = engine.assess("show system info", tool_results=[{"success": True}], llm_output="system info here is detailed")
        assert engine.should_warn(result) is False

    def test_warning_message_format(self, engine):
        result = engine.assess("x", errors=["fail"] * 5)
        msg = engine.warning_message(result)
        assert "Confidence:" in msg
        assert "threshold:" in msg

    def test_warning_empty_above_threshold(self, engine):
        result = engine.assess("good task with a longer description", tool_results=[{"success": True}], llm_output="all good and working well")
        msg = engine.warning_message(result)
        assert msg == ""

    def test_black_box_stats(self, engine):
        for i in range(5):
            engine.assess(f"task {i}", llm_output="ok")
        stats = engine.black_box.stats()
        assert stats["total"] == 5
        assert stats["avg_confidence"] > 0

    def test_no_llm_output_low_confidence(self, engine):
        result = engine.assess("task with no output", llm_output="")
        # With no tools and no output, should be relatively low
        assert result.confidence < 0.65

    def test_uncertain_keywords_lower_score(self, engine):
        result = engine.assess("uncertain task", llm_output="I don't know how to do that")
        normal = engine.assess("normal task", llm_output="here is the answer")
        assert result.confidence < normal.confidence


class TestParseYaml:

    def test_parse_simple_values(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("threshold: 0.65\nmax_entries: 100\nenabled: true\nname: test\n")
        cfg = _parse_yaml(str(f))
        assert cfg["threshold"] == 0.65
        assert cfg["max_entries"] == 100
        assert cfg["enabled"] is True
        assert cfg["name"] == "test"

    def test_parse_sections(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("threshold: 0.5\nblack_box:\n  enabled: true\n  max_entries: 100\n")
        cfg = _parse_yaml(str(f))
        assert cfg["threshold"] == 0.5
        assert cfg["black_box"]["enabled"] is True
        assert cfg["black_box"]["max_entries"] == 100


class TestBlackBoxRecorder:

    def test_memory_db_works(self):
        recorder = BlackBoxRecorder(db_path=":memory:")
        a = Assessment(timestamp="2026-01-01T00:00:00Z", task_goal="test", confidence=0.8, above_threshold=True, threshold=0.5, breakdown="{}", result_summary="ok", duration_ms=10)
        recorder.record(a)
        entries = recorder.get_recent(10)
        assert len(entries) == 1

    def test_record_and_retrieve(self, tmp_path):
        db = str(tmp_path / "bb.db")
        recorder = BlackBoxRecorder(db_path=db)
        for i in range(3):
            a = Assessment(timestamp="2026-01-01T00:00:00Z", task_goal=f"task {i}", confidence=0.5, above_threshold=True, threshold=0.5, breakdown="{}", result_summary="ok", duration_ms=5)
            recorder.record(a)
        entries = recorder.get_recent(10)
        assert len(entries) == 3
        assert entries[0].task_goal == "task 0"
