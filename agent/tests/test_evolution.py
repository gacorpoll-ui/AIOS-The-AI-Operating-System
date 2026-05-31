import pytest
import time
import os
from agent.core.evolution import EvolutionEngine, _parse_yaml
from agent.core.blackbox import TamperProofBlackBox


class TestEvolutionEngine:

    @pytest.fixture
    def bb(self, tmp_path):
        return TamperProofBlackBox(db_dir=str(tmp_path / "bb"))

    @pytest.fixture
    def engine(self, tmp_path, bb):
        config = tmp_path / "evolution.yaml"
        config.write_text(
            "evolution:\n"
            "  enabled: true\n"
            "  cycle_interval: 3600\n"
            "  min_assessments: 5\n"
            "  types:\n"
            "    tool_optimization: true\n"
            "    rule_tuning: true\n"
            "    workflow_discovery: true\n"
            "    error_prevention: true\n"
            "  safety:\n"
            "    max_changes_per_cycle: 5\n"
            "  black_box:\n"
            "    log_evolution_as: SYSTEM\n"
        )
        return EvolutionEngine(config_path=str(config), black_box=bb)

    def test_evolution_disabled(self, tmp_path):
        config = tmp_path / "evo_disabled.yaml"
        config.write_text("evolution:\n  enabled: false\n  cycle_interval: 1\n  min_assessments: 1\n")
        eng = EvolutionEngine(config_path=str(config))
        assert eng.enabled is False
        assert eng.should_run() is False

    def test_can_be_disabled_via_method(self, engine):
        engine.disable()
        assert engine.enabled is False
        assert engine.should_run() is False

    def test_can_be_re_enabled(self, engine):
        engine.disable()
        engine.enable()
        assert engine.enabled is True

    def test_insufficient_data(self, engine):
        result = engine.run_cycle([])
        assert result["status"] == "insufficient_data"

    def test_evolution_completes_with_data(self, engine):
        # Generate fake black box data
        data = []
        for i in range(20):
            data.append({
                "event_type": "assessment",
                "data": {
                    "tool_name": "list_directory" if i % 2 == 0 else "get_system_info",
                    "success": True,
                    "confidence": 0.80,
                },
            })
        # Add some failures
        for i in range(3):
            data.append({
                "event_type": "confidence_anomaly",
                "data": {
                    "tool_name": "kill_process",
                    "success": False,
                    "error": "permission denied",
                },
            })

        result = engine.run_cycle(data)
        assert result["status"] == "completed"
        assert isinstance(result["improvements"], list)

    def test_evolution_logged_to_black_box(self, engine, bb):
        data = [
            {"event_type": "assessment", "data": {"confidence": 0.80}}
            for _ in range(10)
        ]
        engine.run_cycle(data)

        chain = bb.get_chain(20)
        evo_events = [e for e in chain if e.get("event_type") == "evolution_activity"]
        assert len(evo_events) >= 1
        evo_data = evo_events[0]["data"]
        assert evo_data.get("agent") == "SYSTEM"

    def test_disable_logged_to_black_box(self, engine, bb):
        engine.disable()
        chain = bb.get_chain(10)
        disable_events = [e for e in chain if "evolution_disabled" in str(e.get("data", {}).get("type", ""))]
        assert len(disable_events) >= 1

    def test_get_config(self, engine):
        cfg = engine.get_config()
        assert "enabled" in cfg
        assert "cycle_interval" in cfg
        assert cfg["log_as"] == "SYSTEM"


class TestParseYamlEvolution:

    def test_parse_nested_config(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text(
            "evolution:\n"
            "  enabled: true\n"
            "  cycle_interval: 3600\n"
            "  types:\n"
            "    tool_optimization: true\n"
            "    rule_tuning: false\n"
        )
        cfg = _parse_yaml(str(f))
        assert cfg["evolution"]["enabled"] is True
        assert cfg["evolution"]["types"]["tool_optimization"] is True
        assert cfg["evolution"]["types"]["rule_tuning"] is False

    def test_parse_list(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text(
            "evolution:\n"
            "  safety:\n"
            "    require_approval_for:\n"
            "      - security_threshold_change\n"
            "      - new_tool_registration\n"
        )
        cfg = _parse_yaml(str(f))
        assert "security_threshold_change" in cfg["evolution"]["safety"]["require_approval_for"]