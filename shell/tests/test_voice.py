import pytest
from unittest.mock import MagicMock, patch

class TestVoiceInterface:
    
    def test_is_available_returns_bool(self):
        with patch("shell.voice_interface._sounddevice_available", False):
            from shell.voice_interface import VoiceInterface
            vi = VoiceInterface()
            assert isinstance(vi.has_microphone, bool)
            assert vi.has_microphone is False

    def test_speak_completes_without_error_when_unavailable(self):
        with patch("shell.voice_interface._pyttsx3_available", False):
            import importlib
            import shell.voice_interface as vi_mod
            importlib.reload(vi_mod)
            from shell.voice_interface import VoiceInterface
            
            vi = VoiceInterface()
            vi.speak("Hello world")

    def test_voice_mode_flag_changes_shell_behavior(self):
        mock_llm = MagicMock()
        mock_llm.is_loaded = True
        mock_llm.generate_structured.return_value = {
            "intent": "Test", "tool_calls": [], "requires_clarification": False
        }
        mock_llm.generate.return_value = "Done."
        
        mock_tools = MagicMock()
        mock_tools.list_tools.return_value = []
        
        with patch("shell.history.sqlite3"):
            from shell.nl_shell import NLShell
            shell = NLShell(llm=mock_llm, tools=mock_tools, memory=MagicMock())
            
            assert shell.voice_mode is False
            
            shell.voice_mode = not shell.voice_mode
            assert shell.voice_mode is True
            
            shell.voice_mode = not shell.voice_mode
            assert shell.voice_mode is False

    def test_speak_strips_markdown(self):
        import importlib
        import shell.voice_interface as vi_mod
        importlib.reload(vi_mod)
        from shell.voice_interface import VoiceInterface
        
        vi = VoiceInterface()
        
        mock_engine = MagicMock()
        vi._tts_engine = mock_engine
        
        with patch("shell.voice_interface._pyttsx3_available", True):
            vi.speak("**Hello** and backtick_world")
            mock_engine.say.assert_called_once()
            spoken = mock_engine.say.call_args[0][0]
            assert "**" not in spoken
            assert "backtick" in spoken