import pytest
from unittest.mock import MagicMock, patch
from agent.models.cloud_llm import CloudLLM, AIProvider

class TestCloudLLM:

    def test_openai_initialization(self):
        with patch("os.environ.get", return_value="test-key"):
            llm = CloudLLM(AIProvider.OPENAI)
            assert llm.is_loaded is True
            assert llm.provider == AIProvider.OPENAI
            assert llm.model == "gpt-4o-mini"

    def test_anthropic_initialization(self):
        with patch("os.environ.get", return_value="test-key"):
            llm = CloudLLM(AIProvider.ANTHROPIC)
            assert llm.is_loaded is True
            assert llm.provider == AIProvider.ANTHROPIC
            assert llm.model == "claude-sonnet-4-20250514"

    def test_gemini_initialization(self):
        with patch("os.environ.get", return_value="test-key"):
            llm = CloudLLM(AIProvider.GEMINI)
            assert llm.is_loaded is True
            assert llm.provider == AIProvider.GEMINI

    def test_ollama_no_api_key_needed(self):
        llm = CloudLLM(AIProvider.OLLAMA)
        assert llm.is_loaded is True
        assert llm.api_key is None

    def test_unloaded_provider_without_key(self):
        with patch("os.environ.get", return_value=None):
            llm = CloudLLM(AIProvider.OPENAI)
            assert llm.is_loaded is False

    def test_model_info_returns_dict(self):
        with patch("os.environ.get", return_value="test-key"):
            llm = CloudLLM(AIProvider.OPENAI)
            info = llm.model_info
            assert "provider" in info
            assert "model" in info
            assert "base_url" in info

    def test_custom_provider_with_url(self):
        with patch("os.environ.get", return_value=None):
            llm = CloudLLM(AIProvider.CUSTOM, api_key="my-key", base_url="http://my-server:8080/v1")
            assert llm.is_loaded is True
            assert llm.api_key == "my-key"
            assert llm.base_url == "http://my-server:8080/v1"

    def test_generate_structured_parsing(self):
        with patch("os.environ.get", return_value="test-key"):
            llm = CloudLLM(AIProvider.OPENAI)
            with patch.object(llm, "generate", return_value='{"intent": "test", "tool_calls": []}'):
                result = llm.generate_structured("test", {"intent": "string", "tool_calls": []})
                assert result["intent"] == "test"
                assert result["tool_calls"] == []

    def test_generate_structured_fallback(self):
        with patch("os.environ.get", return_value="test-key"):
            llm = CloudLLM(AIProvider.OPENAI)
            with patch.object(llm, "generate", return_value="not valid json {{{"):
                result = llm.generate_structured("test", {"intent": "string"})
                assert "raw_text" in result

    def test_embed_returns_list(self):
        with patch("os.environ.get", return_value="test-key"):
            llm = CloudLLM(AIProvider.OPENAI)
            with patch.object(llm, "_call_openai_embedding", return_value=[0.1, 0.2, 0.3]):
                emb = llm.embed("hello")
                assert isinstance(emb, list)
                assert len(emb) == 3

    def test_embed_unsupported_provider_returns_mock(self):
        llm = CloudLLM(AIProvider.OLLAMA)
        emb = llm.embed("hello")
        assert isinstance(emb, list)
        assert len(emb) == 384

    def test_from_config_creates_default(self, tmp_path):
        config_file = str(tmp_path / "nonexistent.json")
        llm = CloudLLM.from_config(config_file)
        assert llm.provider == AIProvider.OPENAI

    def test_save_and_load_config(self, tmp_path):
        config_file = str(tmp_path / "ai_config.json")
        llm = CloudLLM(AIProvider.CUSTOM, api_key="test-123", model="my-model", base_url="http://localhost:8080")
        llm.save_config(config_file)

        llm2 = CloudLLM.from_config(config_file)
        assert llm2.provider == AIProvider.CUSTOM
        assert llm2.model == "my-model"
        assert llm2.api_key == "test-123"