import os
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class ModelManager:
    """Manages multiple models (main LLM + embedding model)."""
    
    def __init__(self, models_dir: str = "~/.aios/models"):
        self.models_dir = os.path.expanduser(models_dir)
        os.makedirs(self.models_dir, exist_ok=True)
        
    def download_model(self, model_id: str, destination: str) -> bool:
        """Downloads model from HuggingFace."""
        dest_path = os.path.join(self.models_dir, destination)
        logger.info(f"Downloading model {model_id} to {dest_path}")
        
        # In a real implementation we would use huggingface_hub
        # from huggingface_hub import hf_hub_download
        # hf_hub_download(repo_id=repo_id, filename=filename, local_dir=self.models_dir)
        
        logger.info("Model download implementation is a stub")
        return True
        
    def list_available_models(self) -> List[Dict[str, Any]]:
        """Lists available downloaded models."""
        models = []
        if os.path.exists(self.models_dir):
            for file in os.listdir(self.models_dir):
                if file.endswith(".gguf") or file.endswith(".bin"):
                    path = os.path.join(self.models_dir, file)
                    size_mb = os.path.getsize(path) / (1024 * 1024)
                    models.append({
                        "name": file,
                        "path": path,
                        "size_mb": round(size_mb, 2)
                    })
        return models
        
    def get_recommended_model(self, vram_gb: float) -> str:
        """Returns best model name for available VRAM."""
        if vram_gb >= 24.0:
            return "mixtral-8x7b-instruct-v0.1.Q5_K_M.gguf"
        elif vram_gb >= 16.0:
            return "llama-3-70b-instruct.Q3_K_M.gguf"
        elif vram_gb >= 8.0:
            return "llama-3-8b-instruct.Q8_0.gguf"
        elif vram_gb >= 4.0:
            return "phi-3-mini-4k-instruct.Q4_K_M.gguf"
        else:
            return "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
