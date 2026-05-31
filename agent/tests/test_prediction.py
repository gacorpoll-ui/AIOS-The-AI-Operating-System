import pytest
import time
import os
from agent.core.prediction import PredictionEngine, _parse_yaml
from agent.core.blackbox import TamperProofBlackBox


class TestPredictionEngine:

    @pytest.fixture
    def bb(self, tmp_path):
        return TamperProofBlackBox(db_dir=str(tmp_path / "bb"))

    @pytest.fixture
    def engine(self, tmp_path, bb):
        config = tmp_path / "prediction.yaml"
        config.write_text(
            "prediction:\n"
            "  enabled: true\n"
            "  max_cpu_fraction: 0.20\n"
            "  prediction_window: 300\n"
            "  min_history: 3\n"
            "  patterns:\n"
            "    time_based: true\n"
            "    sequence_based: true\n"
            "    frequency_based: true\n"
            "  prewarm:\n"
            "    enabled: true\n"
            "    silent: true\n"
            "    max_items: 3\n"
            "    timeout_seconds: 5\n"
        )
        return PredictionEngine(config_path=str(config), black_box=bb)

    def test_disabled_returns_empty(self, tmp_path):
        config = tmp_path / "pred_disabled.yaml"
        config.write_text("prediction:\n  enabled: false\n  min_history: 1\n")
        eng = PredictionEngine(config_path=str(config))
        assert eng.enabled is False
        assert eng.predict([]) == []

    def test_can_disable(self, engine):
        engine.disable()
        assert engine.enabled is False
        assert engine.should_run() is False

    def test_can_re_enable(self, engine):
        engine.disable()
        engine.enable()
        assert engine.enabled is True

    def test_predict_with_insufficient_data(self, engine):
        result = engine.predict([{"data": {}}])
        assert result == []

    def test_predict_frequency(self, engine):
        history = [
            {"event_type": "assessment", "data": {"tool_name": "list_directory"},
             "timestamp": "2026-01-01T10:00:00+00:00"}
            for _ in range(10)
        ]
        history += [
            {"event_type": "assessment", "data": {"tool_name": "get_system_info"},
             "timestamp": "2026-01-01T10:00:00+00:00"}
            for _ in range(5)
        ]

        predictions = engine.predict(history)
        assert len(predictions) > 0
        freq_preds = [p for p in predictions if p["type"] == "frequency"]
        assert len(freq_preds) > 0
        assert freq_preds[0]["predicted_tool"] == "list_directory"

    def test_predict_sequence(self, engine):
        # Create pattern: list_directory → get_system_info (repeated)
        history = []
        for i in range(8):
            history.append({"event_type": "assessment",
                           "data": {"tool_name": "list_directory"},
                           "timestamp": "2026-01-01T10:00:00+00:00"})
            history.append({"event_type": "assessment",
                           "data": {"tool_name": "get_system_info"},
                           "timestamp": "2026-01-01T10:00:00+00:00"})

        predictions = engine.predict(history)
        seq_preds = [p for p in predictions if p["type"] == "sequence"]
        assert len(seq_preds) > 0
        # Most recent tool is get_system_info, so sequence predicts what follows it
        # Since we always end with get_system_info, the sequence is get_system_info → nothing new
        # So it predicts list_directory (which follows get_system_info in our alternating pattern)
        assert seq_preds[0]["after_tool"] == "get_system_info"

    def test_pre_warm_runs_silently(self, engine):
        history = [
            {"event_type": "assessment", "data": {"tool_name": "list_directory"},
             "timestamp": "2026-01-01T10:00:00+00:00"}
            for _ in range(5)
        ]
        engine.predict(history)
        time.sleep(0.5)  # Let pre-warm thread run

        status = engine.get_prewarm_status()
        assert status["cached_items"] >= 1
        assert "list_directory" in status["cache"]

    def test_get_predictions(self, engine):
        history = [
            {"event_type": "assessment", "data": {"tool_name": "list_directory"},
             "timestamp": "2026-01-01T10:00:00+00:00"}
            for _ in range(5)
        ]
        engine.predict(history)
        preds = engine.get_predictions()
        assert len(preds) > 0
        assert "confidence" in preds[0]
        assert "predicted_tool" in preds[0]

    def test_disable_logged_to_black_box(self, engine, bb):
        engine.disable()
        chain = bb.get_chain(10)
        disable_events = [e for e in chain if "prediction_disabled" in str(e.get("data", {}).get("type", ""))]
        assert len(disable_events) >= 1


class TestParseYamlPrediction:

    def test_parse_nested_prediction_config(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text(
            "prediction:\n"
            "  enabled: true\n"
            "  max_cpu_fraction: 0.20\n"
            "  prewarm:\n"
            "    enabled: true\n"
            "    silent: true\n"
        )
        cfg = _parse_yaml(str(f))
        assert cfg["prediction"]["enabled"] is True
        assert cfg["prediction"]["prewarm"]["silent"] is True