import os
import json
import time
import logging
from typing import Dict, List, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)

class AIProvider(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OLLAMA = "ollama"
    CUSTOM = "custom"
    LOCAL = "local"

class CloudLLM:
    """Unified interface for external AI providers (OpenAI, Anthropic, Gemini, Ollama, custom)."""

    def __init__(
        self,
        provider: AIProvider,
        api_key: Optional[str] = None,
        model: str = None,
        base_url: Optional[str] = None,
        api_version: Optional[str] = None,
        streaming: bool = False,
    ):
        self.provider = provider
        self.api_key = api_key or self._get_default_key(provider)
        self.model = model or self._get_default_model(provider)
        self.base_url = base_url or self._get_default_url(provider)
        self.api_version = api_version
        self.streaming = streaming
        self._is_loaded = bool(self.api_key or provider == AIProvider.OLLAMA)

    @staticmethod
    def _get_default_key(provider: AIProvider) -> Optional[str]:
        keys = {
            AIProvider.OPENAI: os.environ.get("OPENAI_API_KEY"),
            AIProvider.ANTHROPIC: os.environ.get("ANTHROPIC_API_KEY"),
            AIProvider.GEMINI: os.environ.get("GOOGLE_API_KEY"),
            AIProvider.OLLAMA: None,  # Ollama doesn't need API key
            AIProvider.CUSTOM: os.environ.get("CUSTOM_AI_API_KEY"),
        }
        return keys.get(provider)

    @staticmethod
    def _get_default_model(provider: AIProvider) -> str:
        models = {
            AIProvider.OPENAI: "gpt-4o-mini",
            AIProvider.ANTHROPIC: "claude-sonnet-4-20250514",
            AIProvider.GEMINI: "gemini-2.0-flash",
            AIProvider.OLLAMA: "llama3",
            AIProvider.CUSTOM: "custom-model",
        }
        return models.get(provider, "gpt-4o-mini")

    @staticmethod
    def _get_default_url(provider: AIProvider) -> str:
        urls = {
            AIProvider.OPENAI: "https://api.openai.com/v1",
            AIProvider.ANTHROPIC: "https://api.anthropic.com/v1",
            AIProvider.GEMINI: "https://generativelanguage.googleapis.com/v1beta",
            AIProvider.OLLAMA: "http://localhost:11434",
            AIProvider.CUSTOM: os.environ.get("CUSTOM_AI_URL", ""),
        }
        return urls.get(provider, "")

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    @property
    def model_info(self) -> Dict[str, Any]:
        return {
            "provider": self.provider.value,
            "model": self.model,
            "base_url": self.base_url,
        }

    def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        """Generate text response from the AI provider."""
        if not self.is_loaded:
            raise RuntimeError("Cloud LLM not loaded. Provide API key or set env variable.")

        start_time = time.time()

        try:
            if self.provider == AIProvider.OPENAI:
                text = self._call_openai_chat(prompt, max_tokens, temperature)
            elif self.provider == AIProvider.ANTHROPIC:
                text = self._call_anthropic(prompt, max_tokens, temperature)
            elif self.provider == AIProvider.GEMINI:
                text = self._call_gemini(prompt, max_tokens, temperature)
            elif self.provider == AIProvider.OLLAMA:
                text = self._call_ollama(prompt, max_tokens, temperature)
            elif self.provider == AIProvider.CUSTOM:
                text = self._call_openai_chat(prompt, max_tokens, temperature, url_override=self.base_url)
            else:
                text = f"[Unknown provider: {self.provider.value}]"

            inference_time = time.time() - start_time
            logger.info(f"{self.provider.value} inference complete in {inference_time:.2f}s")
            return text
        except Exception as e:
            logger.error(f"{self.provider.value} generation failed: {e}")
            raise

    def generate_structured(self, prompt: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Generate structured JSON output matching a schema."""
        schema_desc = json.dumps(schema, indent=2)
        structured_prompt = (
            f"{prompt}\n\n"
            f"Respond with ONLY valid JSON matching this structure:\n"
            f"{schema_desc}"
        )

        response_text = self.generate(structured_prompt, max_tokens=2048, temperature=0.1)

        # Try to extract JSON from response
        try:
            # Find first { and last }
            start = response_text.index("{")
            end = response_text.rindex("}") + 1
            json_str = response_text[start:end]
            return json.loads(json_str)
        except (ValueError, json.JSONDecodeError):
            logger.warning(f"Failed to parse structured output, returning raw text")
            return {"raw_text": response_text}

    def embed(self, text: str) -> List[float]:
        """Generate embedding vector (OpenAI only for now)."""
        if self.provider == AIProvider.OPENAI:
            return self._call_openai_embedding(text)
        else:
            logger.warning(f"Embedding not supported for {self.provider.value}, returning mock vector")
            return [0.0] * 384

    # --- OpenAI ---
    def _call_openai_chat(self, prompt: str, max_tokens: int, temperature: float, url_override: str = None) -> str:
        import urllib.request
        url = url_override or self.base_url
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": self.streaming,
        }
        data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(f"{url}/chat/completions", data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            content_type = resp.headers.get("Content-Type", "")

            # Streaming response (SSE format)
            if "text/event-stream" in content_type or self.streaming:
                return self._read_stream(resp)

            # Standard JSON response
            result = json.loads(resp.read().decode())
            if "choices" in result and result["choices"]:
                msg = result["choices"][0].get("message")
                if msg and "content" in msg:
                    return msg["content"]
                # Some APIs return content directly in choices[0].text
                delta = result["choices"][0].get("delta")
                if delta and "content" in delta:
                    return delta["content"]
            return ""

    def _read_stream(self, resp) -> str:
        """Read SSE streaming response and assemble full text."""
        full_text = ""
        buffer = b""
        while True:
            chunk = resp.read(4096)
            if not chunk:
                break
            buffer += chunk
            lines = buffer.split(b"\n")
            buffer = lines[-1]
            for line in lines[:-1]:
                line = line.strip()
                if not line or line == b"data: [DONE]":
                    continue
                if line.startswith(b"data: "):
                    try:
                        data_str = line[6:].decode("utf-8", errors="replace")
                        data = json.loads(data_str)
                        choices = data.get("choices", [])
                        if not choices:
                            continue
                        choice = choices[0]
                        delta = choice.get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            full_text += content
                    except (json.JSONDecodeError, UnicodeDecodeError, IndexError):
                        continue
        return full_text

    def _call_openai_embedding(self, text: str) -> List[float]:
        import urllib.request
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        data = json.dumps({
            "model": "text-embedding-3-small",
            "input": text,
        }).encode("utf-8")

        req = urllib.request.Request(f"{self.base_url}/embeddings", data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            return result["data"][0]["embedding"]

    # --- Anthropic (Claude) ---
    def _call_anthropic(self, prompt: str, max_tokens: int, temperature: float) -> str:
        import urllib.request
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        data = json.dumps({
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")

        req = urllib.request.Request(f"{self.base_url}/messages", data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())
            return result["content"][0]["text"]

    # --- Google Gemini ---
    def _call_gemini(self, prompt: str, max_tokens: int, temperature: float) -> str:
        import urllib.request
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        data = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }).encode("utf-8")

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())
            return result["candidates"][0]["content"]["parts"][0]["text"]

    # --- Ollama (local, no API key needed) ---
    def _call_ollama(self, prompt: str, max_tokens: int, temperature: float) -> str:
        import urllib.request
        url = f"{self.base_url}/api/generate"
        headers = {"Content-Type": "application/json"}
        data = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }).encode("utf-8")

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())
            return result.get("response", "")

    @classmethod
    def from_config(cls, config_path: str = "~/.aios/ai_config.json") -> "CloudLLM":
        """Create CloudLLM from config file."""
        path = os.path.expanduser(config_path)
        if os.path.exists(path):
            with open(path, "r") as f:
                cfg = json.load(f)
            provider = AIProvider(cfg.get("provider", "openai"))
            return cls(
                provider=provider,
                api_key=cfg.get("api_key"),
                model=cfg.get("model"),
                base_url=cfg.get("base_url"),
                streaming=cfg.get("streaming", False),
            )
        # No config file, return default OpenAI
        return cls(provider=AIProvider.OPENAI)

    def save_config(self, config_path: str = "~/.aios/ai_config.json") -> None:
        """Save current config to file."""
        path = os.path.expanduser(config_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        cfg = {
            "provider": self.provider.value,
            "api_key": self.api_key,
            "model": self.model,
            "base_url": self.base_url,
            "streaming": self.streaming,
        }
        with open(path, "w") as f:
            json.dump(cfg, f, indent=2)
        logger.info(f"AI config saved to {path}")