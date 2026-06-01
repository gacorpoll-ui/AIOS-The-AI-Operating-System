import pytest
import os
import json
import tempfile
import shutil
from unittest.mock import MagicMock
from agent.core.tool_factory import ToolFactory, ToolProposal, GENERATED_TOOLS_DIR
from agent.core.blackbox import TamperProofBlackBox
from security.constitution import Constitution


class TestToolFactory:

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        Constitution._instance = None
        yield
        Constitution._instance = None

    @pytest.fixture
    def bb(self, tmp_path):
        return TamperProofBlackBox(db_dir=str(tmp_path / "bb"))

    @pytest.fixture
    def factory_dir(self, tmp_path):
        """Create an isolated generated tools directory."""
        gen_dir = str(tmp_path / "generated")
        os.makedirs(gen_dir, exist_ok=True)
        return gen_dir

    @pytest.fixture
    def factory(self, bb, factory_dir, tmp_path):
        # Override the module-level GENERATED_TOOLS_DIR for testing
        import agent.core.tool_factory as tf
        orig_dir = tf.GENERATED_TOOLS_DIR
        tf.GENERATED_TOOLS_DIR = factory_dir

        const = Constitution(black_box=bb)

        factory = ToolFactory(black_box=bb, constitution=const)
        factory._orig_dir = orig_dir
        yield factory
        tf.GENERATED_TOOLS_DIR = orig_dir

    def test_propose_tool_creates_valid_proposal(self, factory):
        proposal = factory.propose_tool(
            name="quick_scan",
            purpose="Quickly scan directory for large files",
            params={"path": str, "max_size": int}
        )
        assert proposal.name == "quick_scan"
        assert "large files" in proposal.purpose
        assert "path" in proposal.params

    def test_create_tool_writes_file(self, factory):
        proposal = factory.propose_tool(
            name="hello_world",
            purpose="Print hello world",
            params={"name": str}
        )
        result = factory.create_tool(proposal)
        assert result["success"] is True
        assert os.path.exists(result["file"])

    def test_generated_tool_is_valid_python(self, factory):
        proposal = factory.propose_tool(
            name="test_tool",
            purpose="Test tool generation",
            params={"x": str}
        )
        result = factory.create_tool(proposal)
        assert result["success"] is True

        # Verify it's valid Python
        with open(result["file"], "r") as f:
            code = f.read()
        compile(code, result["file"], "exec")

    def test_rate_limit_max_5_per_day(self, factory):
        for i in range(5):
            proposal = factory.propose_tool(
                name=f"tool_{i}",
                purpose=f"Tool number {i}"
            )
            result = factory.create_tool(proposal)
            assert result["success"] is True

        # 6th tool should fail
        proposal = factory.propose_tool(
            name="tool_5",
            purpose="Tool over limit"
        )
        result = factory.create_tool(proposal)
        assert result["success"] is False
        assert result["reason"] == "rate_limit"

    def test_remove_tool_deletes_file(self, factory):
        proposal = factory.propose_tool(
            name="removable_tool",
            purpose="This tool can be removed"
        )
        factory.create_tool(proposal)

        result = factory.remove_tool("removable_tool")
        assert result["success"] is True

        func_name = "removable_tool"
        tool_file = os.path.join(factory._orig_dir.__class__.__bases__[0].__module__.replace('.', '/'),
                                 "tools", "generated", f"{func_name}.py")
        # Check in the actual factory dir
        import agent.core.tool_factory as tf
        tool_file = os.path.join(tf.GENERATED_TOOLS_DIR, f"{func_name}.py")
        assert not os.path.exists(tool_file)

    def test_remove_nonexistent_tool_returns_error(self, factory):
        result = factory.remove_tool("nonexistent_tool")
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_list_generated_tools(self, factory):
        for i in range(3):
            proposal = factory.propose_tool(
                name=f"listable_{i}",
                purpose=f"Tool {i} for listing"
            )
            factory.create_tool(proposal)

        tools = factory.list_generated_tools()
        assert len(tools) == 3
        names = [t["name"] for t in tools]
        assert "listable_0" in names

    def test_rate_limit_status(self, factory):
        for i in range(2):
            proposal = factory.propose_tool(
                name=f"rate_test_{i}",
                purpose=f"Rate test {i}"
            )
            factory.create_tool(proposal)

        status = factory.get_rate_limit_status()
        assert status["created_today"] == 2
        assert status["remaining"] == 3

    def test_tool_creation_logged_to_black_box(self, factory, bb):
        proposal = factory.propose_tool(
            name="logged_tool",
            purpose="This should be logged"
        )
        factory.create_tool(proposal)

        chain = bb.get_chain(20)
        creation_events = [e for e in chain if e.get("event_type") == "tool_creation"]
        assert len(creation_events) >= 1
        assert creation_events[0]["data"]["tool_name"] == "logged_tool"

    def test_tool_removal_logged_to_black_box(self, factory, bb):
        proposal = factory.propose_tool(
            name="removable_for_log",
            purpose="Will be removed and logged"
        )
        factory.create_tool(proposal)
        factory.remove_tool("removable_for_log")

        chain = bb.get_chain(20)
        removal_events = [e for e in chain if e.get("event_type") == "tool_removal"]
        assert len(removal_events) >= 1

    def test_tool_name_sanitized(self, factory):
        proposal = factory.propose_tool(
            name="bad-name with spaces!",
            purpose="Test name sanitization"
        )
        result = factory.create_tool(proposal)
        assert result["success"] is True
        assert result["func_name"] == "bad_name_with_spaces_"

    def test_parliament_rejection_blocks_tool(self, factory):
        # Create a mock parliament that rejects
        mock_parliament = MagicMock()
        mock_verdict = MagicMock()
        mock_verdict.verdict = "REJECT"
        mock_parliament.convene.return_value = mock_verdict

        factory.parliament = mock_parliament
        proposal = factory.propose_tool(
            name="rejected_tool",
            purpose="This will be rejected"
        )
        result = factory.create_tool(proposal)
        assert result["success"] is False
        assert result["reason"] == "parliament_rejected"
