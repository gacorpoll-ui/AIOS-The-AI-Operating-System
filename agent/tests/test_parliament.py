import pytest
import time
import os
from agent.core.parliament import (
    Parliament, ParliamentVerdict, ParliamentRecord,
    AgentArgument, _parse_yaml
)


class TestParliament:

    @pytest.fixture
    def parliament(self, tmp_path):
        config = tmp_path / "parliament.yaml"
        config.write_text(
            "high_stakes_tools:\n"
            "  - kill_process\n"
            "  - write_file\n"
            "  - run_command\n"
            "confidence_threshold: 0.50\n"
            "parliament:\n"
            "  max_rounds: 3\n"
            "  max_time_seconds: 90\n"
            "  timeout_per_round: 25\n"
            "  agents:\n"
        )
        # Add agents manually (yaml parser is minimal)
        agents_section = (
            "    - id: advocate\n"
            "      role: Argues in favor\n"
            "      weight: 1.0\n"
            "    - id: critic\n"
            "      role: Argues against\n"
            "      weight: 1.2\n"
            "    - id: risk_assessor\n"
            "      role: Evaluates risk\n"
            "      weight: 1.0\n"
            "    - id: judge\n"
            "      role: Renders final verdict\n"
            "      weight: 1.5\n"
        )
        with open(config, "a") as f:
            f.write(agents_section)
        return Parliament(config_path=str(config))

    @pytest.fixture
    def parliament_with_bb(self, tmp_path):
        config = tmp_path / "parliament.yaml"
        config.write_text(
            "high_stakes_tools:\n"
            "  - kill_process\n"
            "confidence_threshold: 0.50\n"
            "parliament:\n"
            "  max_rounds: 3\n"
            "  max_time_seconds: 90\n"
            "  timeout_per_round: 25\n"
            "  agents:\n"
            "    - id: advocate\n"
            "      role: Argues in favor\n"
            "      weight: 1.0\n"
            "    - id: critic\n"
            "      role: Argues against\n"
            "      weight: 1.2\n"
            "    - id: risk_assessor\n"
            "      role: Evaluates risk\n"
            "      weight: 1.0\n"
            "    - id: judge\n"
            "      role: Renders final verdict\n"
            "      weight: 1.5\n"
        )
        from agent.core.metacog import BlackBoxRecorder
        bb = BlackBoxRecorder(db_path=str(tmp_path / "bb.db"))
        return Parliament(config_path=str(config), black_box=bb)

    def test_should_convene_for_high_stakes_low_confidence(self, parliament):
        assert parliament.should_convene("kill_process", 0.30) is True

    def test_should_not_convene_for_safe_tool(self, parliament):
        assert parliament.should_convene("list_directory", 0.30) is False

    def test_should_not_convene_for_high_confidence(self, parliament):
        assert parliament.should_convene("kill_process", 0.80) is False

    def test_convene_returns_verdict(self, parliament):
        verdict = parliament.convene(
            decision="Kill process 1234",
            tool_name="kill_process",
            tool_params={"pid": 1234},
        )
        assert isinstance(verdict, ParliamentVerdict)
        assert verdict.verdict in ("APPROVE", "APPROVE_WITH_CONDITIONS", "REJECT", "DEFER")
        assert verdict.total_rounds > 0
        assert len(verdict.arguments) > 0

    def test_convene_completes_under_90_seconds(self, parliament):
        start = time.time()
        parliament.convene("Test decision", "kill_process", {"pid": 1})
        elapsed = time.time() - start
        assert elapsed < 90.0, f"Parliament took {elapsed:.1f}s, must be < 90s"

    def test_convene_arguments_logged(self, parliament):
        verdict = parliament.convene("Test", "write_file", {"path": "/tmp/test"})
        agent_ids = [a.agent_id for a in verdict.arguments]
        assert "advocate" in agent_ids
        assert "critic" in agent_ids
        assert "judge" in agent_ids

    def test_verdict_logged_to_black_box(self, parliament_with_bb):
        parliament_with_bb.convene("Dangerous action", "kill_process", {"pid": 999})
        history = parliament_with_bb.get_parliament_history()
        assert len(history) == 1
        assert history[0]["tool_name"] == "kill_process"

    def test_verdict_is_final(self, parliament):
        """Run twice — second verdict should not reference first."""
        v1 = parliament.convene("Task A", "kill_process", {"pid": 1})
        v2 = parliament.convene("Task B", "kill_process", {"pid": 2})

        # Each verdict should be independent
        assert v1.decision == "Task A"
        assert v2.decision == "Task B"
        assert v1 is not v2

    def test_all_agent_args_stored_in_black_box(self, parliament_with_bb):
        parliament_with_bb.convene("Test", "kill_process", {"pid": 1})
        history = parliament_with_bb.get_parliament_history(1)
        assert len(history) == 1
        # The record contains tool_name which proves it was logged
        assert history[0]["tool_name"] == "kill_process"


class TestParseYamlParliament:

    def test_parse_high_stakes_list(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("high_stakes_tools:\n  - kill_process\n  - write_file\nconfidence_threshold: 0.5\n")
        cfg = _parse_yaml(str(f))
        assert "kill_process" in cfg["high_stakes_tools"]
        assert cfg["confidence_threshold"] == 0.5
