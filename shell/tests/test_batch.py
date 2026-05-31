import pytest
from unittest.mock import MagicMock, patch
from shell.nl_shell import NLShell


class TestBatchMode:

    @pytest.fixture
    def shell(self):
        mock_llm = MagicMock()
        mock_llm.is_loaded = True
        mock_llm.generate_structured.return_value = {
            "intent": "test",
            "tool_calls": [],
            "requires_clarification": False,
        }
        mock_llm.generate.return_value = "OK"

        mock_tools = MagicMock()
        mock_tools.list_tools.return_value = []

        with patch("shell.history.sqlite3"):
            return NLShell(llm=mock_llm, tools=mock_tools, memory=MagicMock())

    def test_run_batch_executes_all_tasks(self, shell):
        tasks = [
            {"goal": "show files"},
            {"goal": "show system info"},
        ]
        results = shell.run_batch(tasks)

        assert len(results) == 2
        assert results[0]["task"] == "show files"
        assert results[1]["task"] == "show system info"

    def test_run_batch_handles_empty_goal(self, shell):
        tasks = [
            {"goal": ""},
            {"goal": "show files"},
        ]
        results = shell.run_batch(tasks)
        assert len(results) == 1
        assert results[0]["task"] == "show files"

    def test_run_batch_handles_missing_goal_key(self, shell):
        tasks = [
            {"command": "show files"},
        ]
        results = shell.run_batch(tasks)
        assert len(results) == 1
        assert results[0]["task"] == "show files"

    def test_run_batch_returns_summary(self, shell):
        tasks = [
            {"goal": "show files"},
        ]
        results = shell.run_batch(tasks)
        # Each result dict should have success key
        assert "success" in results[0]
        assert "message" in results[0]
        assert "tool_calls" in results[0]
