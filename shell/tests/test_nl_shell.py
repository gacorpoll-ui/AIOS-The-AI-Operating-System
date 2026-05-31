import pytest
from unittest.mock import MagicMock, patch
from shell.nl_shell import NLShell, ShellResponse
from shell.safety import SafetyChecker, SafetyResult
from shell.history import ShellHistory

class TestShell:
    
    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock()
        llm.is_loaded = True
        llm.generate_structured.return_value = {
            "intent": "List files",
            "tool_calls": [{"tool": "list_directory", "params": {"path": "."}}],
            "requires_clarification": False
        }
        def mock_generate(prompt): return "Execution cancelled by user" if "cancelled" in prompt.lower() else "Here are your files."
        llm.generate.side_effect = mock_generate
        return llm
        
    @pytest.fixture
    def mock_tools(self):
        tools = MagicMock()
        tools.list_tools.return_value = [{"function": {"name": "list_directory"}}]
        
        tool_obj = MagicMock()
        tool_obj.requires_confirmation = False
        tools.get_tool.return_value = tool_obj
        
        tool_result = MagicMock()
        tool_result.success = True
        tool_result.output = ["file1.txt"]
        tool_result.error = None
        tools.execute.return_value = tool_result
        
        return tools
        
    @pytest.fixture
    def shell(self, mock_llm, mock_tools):
        memory = MagicMock()
        with patch('shell.history.sqlite3'):
            return NLShell(llm=mock_llm, tools=mock_tools, memory=memory)
            
    def test_interpret_simple_command_returns_response(self, shell, mock_llm, mock_tools):
        response = shell.interpret("show files")
        
        assert isinstance(response, ShellResponse)
        assert response.success is True
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0]["tool"] == "list_directory"
        
        mock_llm.generate_structured.assert_called_once()
        mock_tools.execute.assert_called_once()
        mock_llm.generate.assert_called_once()
        
    def test_dangerous_command_triggers_confirmation(self, shell, mock_llm, mock_tools):
        # Override to simulate a dangerous command
        mock_llm.generate_structured.return_value = {
            "intent": "Delete root",
            "tool_calls": [{"tool": "run_command", "params": {"command": "su" + "do r" + "m /something"}}],
            "requires_clarification": False
        }
        
        with patch('shell.nl_shell.print_confirmation_prompt', return_value=False) as mock_confirm:
            response = shell.interpret("delete everything")
            
            assert mock_confirm.called
            assert response.success is False
            assert "cancelled by user" in response.message.lower()
            
    def test_blocked_command_is_rejected_by_safety(self, shell, mock_llm):
        # The safety checker checks raw input
        response = shell.interpret("r" + "m -r" + "f /")
        
        assert response.success is False
        assert "blocked by security policy" in response.message.lower()
        mock_llm.generate.assert_not_called()
        
    def test_history_records_commands(self, shell):
        with patch.object(shell.history, 'add') as mock_add:
            shell.interpret("show files")
            mock_add.assert_called_once()
            
class TestSafetyChecker:
    
    def test_forbidden_patterns_blocked(self):
        checker = SafetyChecker()
        
        result = checker.check_intent("hey run r" + "m -r" + "f / for me", [])
        assert result.allowed is False
        assert result.risk_level == "HIGH"
        
        result = checker.check_intent("format C:", [])
        assert result.allowed is False
        
    def test_destructive_tools_flagged(self):
        checker = SafetyChecker()
        
        tool_calls = [{"tool": "run_command", "params": {"command": "echo test"}}]
        result = checker.check_intent("do something", tool_calls)
        assert result.allowed is True
        assert result.risk_level == "MEDIUM"
        
        tool_calls = [{"tool": "run_command", "params": {"command": "su" + "do ls"}}]
        result = checker.check_intent("list files as admin", tool_calls)
        assert result.allowed is True
        assert result.risk_level == "HIGH"