import os
import pytest
import tempfile
from agent.core.tool_registry import Tool, ToolRegistry, ConfirmationRequired
from agent.tools.filesystem_tools import read_file, list_directory
from agent.tools.process_tools import run_command

class TestTools:
    
    @pytest.fixture
    def registry(self):
        return ToolRegistry(db_path=":memory:")
        
    def test_registry_registers_and_retrieves(self, registry):
        def dummy_tool(x): return x * 2
        
        tool = Tool("double", "Doubles a number", {"type": "object", "properties": {"x": {"type": "integer"}}})
        registry.register(tool, dummy_tool)
        
        retrieved = registry.get_tool("double")
        assert retrieved is not None
        assert retrieved.name == "double"
        
    def test_execute_returns_tool_result(self, registry):
        def add(a, b): return a + b
        
        tool = Tool("add", "Adds numbers", {})
        registry.register(tool, add)
        
        result = registry.execute("add", {"a": 2, "b": 3})
        
        assert result.success is True
        assert result.output == 5
        assert result.error is None
        
    def test_dangerous_commands_require_confirmation(self, registry):
        def dangerous_action(): return "deleted everything"
        
        tool = Tool("delete_all", "Deletes data", {}, requires_confirmation=True)
        registry.register(tool, dangerous_action)
        
        with pytest.raises(ConfirmationRequired):
            registry.execute("delete_all", {})
            
        result = registry.execute("delete_all", {}, confirmed=True)
        assert result.success is True
        
    def test_blocked_commands_are_rejected(self):
        with pytest.raises(ValueError, match="blocked by safety policy"):
            run_command("r" + "m -r" + "f /something")
            
    def test_read_file_works(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("Line 1\nLine 2\nLine 3")
            temp_path = f.name
            
        try:
            content = read_file(temp_path)
            assert "Line 1" in content
            assert "Line 3" in content
            
            with pytest.raises(FileNotFoundError):
                read_file(temp_path + "_nonexistent")
        finally:
            os.unlink(temp_path)
            
    def test_list_directory_returns_list(self):
        results = list_directory(".")
        assert isinstance(results, list)
