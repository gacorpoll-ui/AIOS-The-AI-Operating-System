import os
import pytest
import tempfile
from agent.models.llm_interface import LocalLLM

class TestLocalLLM:
    
    @pytest.fixture
    def mock_model_file(self):
        # Create a temporary dummy file to act as the model file
        fd, path = tempfile.mkstemp(suffix=".gguf")
        with os.fdopen(fd, 'w') as f:
            f.write("mock model data")
        yield path
        os.remove(path)
        
    def test_model_loads_correctly(self, mock_model_file):
        llm = LocalLLM()
        assert not llm.is_loaded
        
        llm.load(model_path=mock_model_file, n_ctx=1024, n_gpu_layers=0)
        
        assert llm.is_loaded
        info = llm.model_info
        assert info["context_size"] == 1024
        assert info["gpu_layers"] == 0
        
    def test_load_nonexistent_model_raises_error(self):
        llm = LocalLLM()
        with pytest.raises(FileNotFoundError):
            llm.load(model_path="/path/to/nowhere/model.gguf")
            
    def test_generate_returns_string(self, mock_model_file):
        llm = LocalLLM()
        llm.load(model_path=mock_model_file)
        
        result = llm.generate(prompt="Hello world")
        assert isinstance(result, str)
        assert len(result) > 0
        
    def test_generate_without_load_raises_error(self):
        llm = LocalLLM()
        with pytest.raises(RuntimeError):
            llm.generate(prompt="Hello")
            
    def test_generate_structured_returns_dict(self, mock_model_file):
        llm = LocalLLM()
        llm.load(model_path=mock_model_file)
        
        schema = {
            "name": "string",
            "age": "number"
        }
        
        result = llm.generate_structured(prompt="Extract info", schema=schema)
        assert isinstance(result, dict)
        assert "name" in result
        assert "age" in result
        
    def test_embed_returns_list_of_floats(self, mock_model_file):
        llm = LocalLLM()
        llm.load(model_path=mock_model_file)
        
        result = llm.embed(text="Hello world")
        assert isinstance(result, list)
        assert len(result) > 0
        assert isinstance(result[0], float)
