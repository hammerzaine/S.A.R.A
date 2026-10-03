"""S.A.R.A Agent Integration — Multi-Provider Web UI Bridge

This module provides a unified interface to multiple AI providers:
- Ollama (local)
- OpenAI (ChatGPT)
- Google Gemini
- GitHub Copilot
- Anthropic Claude
- OpenRouter (access to many models)

Each provider is configured via environment variables or config.yaml.
"""

from __future__ import annotations

import os
import sys
import json
import threading
import requests
from pathlib import Path
from typing import Optional, Callable, Dict, Any

# Add the SaraAgent directory to the path
SARA_ROOT = Path(__file__).parent
sys.path.insert(0, str(SARA_ROOT))

# Set HERMES_HOME if not set
if "HERMES_HOME" not in os.environ:
    os.environ["HERMES_HOME"] = str(SARA_ROOT)


class BaseProvider:
    """Base class for AI providers."""

    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self._initialized = False
        self._init_error = None

    def initialize(self) -> bool:
        """Initialize the provider."""
        raise NotImplementedError

    def chat(self, message: str, stream_callback: Optional[Callable[[str], None]] = None) -> str:
        """Send a message and return the response."""
        raise NotImplementedError

    def is_ready(self) -> bool:
        return self._initialized

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "initialized": self._initialized,
            "error": self._init_error,
        }


class OpenAIProvider(BaseProvider):
    """OpenAI ChatGPT provider."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("openai", config)
        self._api_key = config.get("api_key", os.environ.get("OPENAI_API_KEY", ""))
        self._model = config.get("model", "gpt-4o")
        self._base_url = config.get("base_url", "https://api.openai.com/v1")

    def initialize(self) -> bool:
        if self._initialized:
            return True
        if not self._api_key:
            self._init_error = "OpenAI API key not configured"
            return False
        try:
            response = requests.get(
                f"{self._base_url}/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10,
            )
            if response.status_code != 200:
                self._init_error = f"OpenAI API returned status {response.status_code}"
                return False
            self._initialized = True
            return True
        except Exception as e:
            self._init_error = str(e)
            return False

    def chat(self, message: str, stream_callback: Optional[Callable[[str], None]] = None) -> str:
        if not self._initialized:
            if not self.initialize():
                return f"Error: {self._init_error}"
        try:
            if stream_callback:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": True},
                    stream=True, timeout=120,
                )
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if "choices" in data and data["choices"]:
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_response += content
                                stream_callback(content)
                return full_response
            else:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": False},
                    timeout=120,
                )
                if response.status_code != 200:
                    return f"Error: OpenAI API returned status {response.status_code}"
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Error: {str(e)}"


class GeminiProvider(BaseProvider):
    """Google Gemini provider."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("gemini", config)
        self._api_key = config.get("api_key", os.environ.get("GEMINI_API_KEY", ""))
        self._model = config.get("model", "gemini-2.0-flash")
        self._base_url = config.get("base_url", "https://generativelanguage.googleapis.com/v1beta")

    def _get_endpoint(self) -> str:
        """Build the correct Gemini API endpoint."""
        return f"{self._base_url}/models/{self._model}:generateContent?key={self._api_key}"

    def initialize(self) -> bool:
        if self._initialized:
            return True
        if not self._api_key:
            self._init_error = "Gemini API key not configured"
            return False
        try:
            response = requests.get(
                f"{self._base_url}/models?key={self._api_key}",
                timeout=10,
            )
            if response.status_code != 200:
                self._init_error = f"Gemini API returned status {response.status_code}"
                return False
            self._initialized = True
            return True
        except Exception as e:
            self._init_error = str(e)
            return False

    def chat(self, message: str, stream_callback: Optional[Callable[[str], None]] = None) -> str:
        if not self._initialized:
            if not self.initialize():
                return f"Error: {self._init_error}"
        try:
            url = self._get_endpoint()
            if stream_callback:
                url += "&alt=sse"
                response = requests.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": message}]}]},
                    stream=True, timeout=120,
                )
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if "candidates" in data and data["candidates"]:
                            content = data["candidates"][0].get("content", {})
                            parts = content.get("parts", [])
                            for part in parts:
                                text = part.get("text", "")
                                if text:
                                    full_response += text
                                    stream_callback(text)
                return full_response
            else:
                response = requests.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": message}]}]},
                    timeout=120,
                )
                if response.status_code != 200:
                    error_detail = ""
                    try:
                        error_data = response.json()
                        error_detail = f" - {error_data.get('error', {}).get('message', '')}"
                    except Exception:
                        pass
                    return f"Error: Gemini API returned status {response.status_code}{error_detail}"
                data = response.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            return f"Error: {str(e)}"


class CopilotProvider(BaseProvider):
    """GitHub Copilot provider."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("copilot", config)
        self._api_key = config.get("api_key", os.environ.get("COPILOT_GITHUB_TOKEN", ""))
        self._model = config.get("model", "gpt-4o")
        self._base_url = config.get("base_url", "https://api.githubcopilot.com")

    def initialize(self) -> bool:
        if self._initialized:
            return True
        if not self._api_key:
            self._init_error = "GitHub Copilot token not configured"
            return False
        try:
            response = requests.get(
                f"{self._base_url}/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10,
            )
            if response.status_code != 200:
                self._init_error = f"Copilot API returned status {response.status_code}"
                return False
            self._initialized = True
            return True
        except Exception as e:
            self._init_error = str(e)
            return False

    def chat(self, message: str, stream_callback: Optional[Callable[[str], None]] = None) -> str:
        if not self._initialized:
            if not self.initialize():
                return f"Error: {self._init_error}"
        try:
            if stream_callback:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": True},
                    stream=True, timeout=120,
                )
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if "choices" in data and data["choices"]:
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_response += content
                                stream_callback(content)
                return full_response
            else:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": False},
                    timeout=120,
                )
                if response.status_code != 200:
                    return f"Error: Copilot API returned status {response.status_code}"
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Error: {str(e)}"


class AnthropicProvider(BaseProvider):
    """Anthropic Claude provider."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("anthropic", config)
        self._api_key = config.get("api_key", os.environ.get("ANTHROPIC_API_KEY", ""))
        self._model = config.get("model", "claude-sonnet-4")
        self._base_url = config.get("base_url", "https://api.anthropic.com/v1")

    def initialize(self) -> bool:
        if self._initialized:
            return True
        if not self._api_key:
            self._init_error = "Anthropic API key not configured"
            return False
        try:
            response = requests.get(
                f"{self._base_url}/models",
                headers={"x-api-key": self._api_key, "anthropic-version": "2023-06-01"},
                timeout=10,
            )
            if response.status_code != 200:
                self._init_error = f"Anthropic API returned status {response.status_code}"
                return False
            self._initialized = True
            return True
        except Exception as e:
            self._init_error = str(e)
            return False

    def chat(self, message: str, stream_callback: Optional[Callable[[str], None]] = None) -> str:
        if not self._initialized:
            if not self.initialize():
                return f"Error: {self._init_error}"
        try:
            if stream_callback:
                response = requests.post(
                    f"{self._base_url}/messages",
                    headers={"x-api-key": self._api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": True, "max_tokens": 4096},
                    stream=True, timeout=120,
                )
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if data.get("type") == "content_block_delta":
                            text = data.get("delta", {}).get("text", "")
                            if text:
                                full_response += text
                                stream_callback(text)
                return full_response
            else:
                response = requests.post(
                    f"{self._base_url}/messages",
                    headers={"x-api-key": self._api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": False, "max_tokens": 4096},
                    timeout=120,
                )
                if response.status_code != 200:
                    return f"Error: Anthropic API returned status {response.status_code}"
                data = response.json()
                return data["content"][0]["text"]
        except Exception as e:
            return f"Error: {str(e)}"


class OpenRouterProvider(BaseProvider):
    """OpenRouter provider (access to many models)."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("openrouter", config)
        self._api_key = config.get("api_key", os.environ.get("OPENROUTER_API_KEY", ""))
        self._model = config.get("model", "openai/gpt-4o")
        self._base_url = config.get("base_url", "https://openrouter.ai/api/v1")

    def initialize(self) -> bool:
        if self._initialized:
            return True
        if not self._api_key:
            self._init_error = "OpenRouter API key not configured"
            return False
        try:
            response = requests.get(
                f"{self._base_url}/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10,
            )
            if response.status_code != 200:
                self._init_error = f"OpenRouter API returned status {response.status_code}"
                return False
            self._initialized = True
            return True
        except Exception as e:
            self._init_error = str(e)
            return False

    def chat(self, message: str, stream_callback: Optional[Callable[[str], None]] = None) -> str:
        if not self._initialized:
            if not self.initialize():
                return f"Error: {self._init_error}"
        try:
            if stream_callback:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": True},
                    stream=True, timeout=120,
                )
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if "choices" in data and data["choices"]:
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_response += content
                                stream_callback(content)
                return full_response
            else:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": False},
                    timeout=120,
                )
                if response.status_code != 200:
                    return f"Error: OpenRouter API returned status {response.status_code}"
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Error: {str(e)}"



class GroqProvider(BaseProvider):
    """Groq provider (fast inference, free tier available)."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("groq", config)
        self._api_key = config.get("api_key", os.environ.get("GROQ_API_KEY", ""))
        self._model = config.get("model", "llama-3.3-70b-versatile")
        self._base_url = config.get("base_url", "https://api.groq.com/openai/v1")

    def initialize(self) -> bool:
        if self._initialized:
            return True
        if not self._api_key:
            self._init_error = "Groq API key not configured"
            return False
        try:
            response = requests.get(
                f"{self._base_url}/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10,
            )
            if response.status_code != 200:
                self._init_error = f"Groq API returned status {response.status_code}"
                return False
            self._initialized = True
            return True
        except Exception as e:
            self._init_error = str(e)
            return False

    def chat(self, message: str, stream_callback: Optional[Callable[[str], None]] = None) -> str:
        if not self._initialized:
            if not self.initialize():
                return f"Error: {self._init_error}"
        try:
            if stream_callback:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": True},
                    stream=True, timeout=120,
                )
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if "choices" in data and data["choices"]:
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_response += content
                                stream_callback(content)
                return full_response
            else:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": False},
                    timeout=120,
                )
                if response.status_code != 200:
                    return f"Error: Groq API returned status {response.status_code}"
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Error: {str(e)}"


class MistralProvider(BaseProvider):
    """Mistral AI provider."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("mistral", config)
        self._api_key = config.get("api_key", os.environ.get("MISTRAL_API_KEY", ""))
        self._model = config.get("model", "mistral-large-latest")
        self._base_url = config.get("base_url", "https://api.mistral.ai/v1")

    def initialize(self) -> bool:
        if self._initialized:
            return True
        if not self._api_key:
            self._init_error = "Mistral API key not configured"
            return False
        try:
            response = requests.get(
                f"{self._base_url}/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10,
            )
            if response.status_code != 200:
                self._init_error = f"Mistral API returned status {response.status_code}"
                return False
            self._initialized = True
            return True
        except Exception as e:
            self._init_error = str(e)
            return False

    def chat(self, message: str, stream_callback: Optional[Callable[[str], None]] = None) -> str:
        if not self._initialized:
            if not self.initialize():
                return f"Error: {self._init_error}"
        try:
            if stream_callback:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": True},
                    stream=True, timeout=120,
                )
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if "choices" in data and data["choices"]:
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_response += content
                                stream_callback(content)
                return full_response
            else:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": False},
                    timeout=120,
                )
                if response.status_code != 200:
                    return f"Error: Mistral API returned status {response.status_code}"
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Error: {str(e)}"


class DeepSeekProvider(BaseProvider):
    """DeepSeek provider."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("deepseek", config)
        self._api_key = config.get("api_key", os.environ.get("DEEPSEEK_API_KEY", ""))
        self._model = config.get("model", "deepseek-chat")
        self._base_url = config.get("base_url", "https://api.deepseek.com/v1")

    def initialize(self) -> bool:
        if self._initialized:
            return True
        if not self._api_key:
            self._init_error = "DeepSeek API key not configured"
            return False
        try:
            response = requests.get(
                f"{self._base_url}/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10,
            )
            if response.status_code != 200:
                self._init_error = f"DeepSeek API returned status {response.status_code}"
                return False
            self._initialized = True
            return True
        except Exception as e:
            self._init_error = str(e)
            return False

    def chat(self, message: str, stream_callback: Optional[Callable[[str], None]] = None) -> str:
        if not self._initialized:
            if not self.initialize():
                return f"Error: {self._init_error}"
        try:
            if stream_callback:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": True},
                    stream=True, timeout=120,
                )
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if "choices" in data and data["choices"]:
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_response += content
                                stream_callback(content)
                return full_response
            else:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": False},
                    timeout=120,
                )
                if response.status_code != 200:
                    return f"Error: DeepSeek API returned status {response.status_code}"
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Error: {str(e)}"


class XAIProvider(BaseProvider):
    """xAI (Grok) provider."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("xai", config)
        self._api_key = config.get("api_key", os.environ.get("XAI_API_KEY", ""))
        self._model = config.get("model", "grok-2-latest")
        self._base_url = config.get("base_url", "https://api.x.ai/v1")

    def initialize(self) -> bool:
        if self._initialized:
            return True
        if not self._api_key:
            self._init_error = "xAI API key not configured"
            return False
        try:
            response = requests.get(
                f"{self._base_url}/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10,
            )
            if response.status_code != 200:
                self._init_error = f"xAI API returned status {response.status_code}"
                return False
            self._initialized = True
            return True
        except Exception as e:
            self._init_error = str(e)
            return False

    def chat(self, message: str, stream_callback: Optional[Callable[[str], None]] = None) -> str:
        if not self._initialized:
            if not self.initialize():
                return f"Error: {self._init_error}"
        try:
            if stream_callback:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": True},
                    stream=True, timeout=120,
                )
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if "choices" in data and data["choices"]:
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_response += content
                                stream_callback(content)
                return full_response
            else:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": False},
                    timeout=120,
                )
                if response.status_code != 200:
                    return f"Error: xAI API returned status {response.status_code}"
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Error: {str(e)}"


class TogetherProvider(BaseProvider):
    """Together AI provider."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("together", config)
        self._api_key = config.get("api_key", os.environ.get("TOGETHER_API_KEY", ""))
        self._model = config.get("model", "meta-llama/Llama-3.3-70B-Instruct-Turbo")
        self._base_url = config.get("base_url", "https://api.together.xyz/v1")

    def initialize(self) -> bool:
        if self._initialized:
            return True
        if not self._api_key:
            self._init_error = "Together API key not configured"
            return False
        try:
            response = requests.get(
                f"{self._base_url}/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10,
            )
            if response.status_code != 200:
                self._init_error = f"Together API returned status {response.status_code}"
                return False
            self._initialized = True
            return True
        except Exception as e:
            self._init_error = str(e)
            return False

    def chat(self, message: str, stream_callback: Optional[Callable[[str], None]] = None) -> str:
        if not self._initialized:
            if not self.initialize():
                return f"Error: {self._init_error}"
        try:
            if stream_callback:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": True},
                    stream=True, timeout=120,
                )
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if "choices" in data and data["choices"]:
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_response += content
                                stream_callback(content)
                return full_response
            else:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": False},
                    timeout=120,
                )
                if response.status_code != 200:
                    return f"Error: Together API returned status {response.status_code}"
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Error: {str(e)}"


class FireworksProvider(BaseProvider):
    """Fireworks AI provider."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("fireworks", config)
        self._api_key = config.get("api_key", os.environ.get("FIREWORKS_API_KEY", ""))
        self._model = config.get("model", "accounts/fireworks/models/llama-v3p3-70b-instruct")
        self._base_url = config.get("base_url", "https://api.fireworks.ai/inference/v1")

    def initialize(self) -> bool:
        if self._initialized:
            return True
        if not self._api_key:
            self._init_error = "Fireworks API key not configured"
            return False
        try:
            response = requests.get(
                f"{self._base_url}/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10,
            )
            if response.status_code != 200:
                self._init_error = f"Fireworks API returned status {response.status_code}"
                return False
            self._initialized = True
            return True
        except Exception as e:
            self._init_error = str(e)
            return False

    def chat(self, message: str, stream_callback: Optional[Callable[[str], None]] = None) -> str:
        if not self._initialized:
            if not self.initialize():
                return f"Error: {self._init_error}"
        try:
            if stream_callback:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": True},
                    stream=True, timeout=120,
                )
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if "choices" in data and data["choices"]:
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_response += content
                                stream_callback(content)
                return full_response
            else:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": False},
                    timeout=120,
                )
                if response.status_code != 200:
                    return f"Error: Fireworks API returned status {response.status_code}"
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Error: {str(e)}"


class PerplexityProvider(BaseProvider):
    """Perplexity provider."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("perplexity", config)
        self._api_key = config.get("api_key", os.environ.get("PERPLEXITY_API_KEY", ""))
        self._model = config.get("model", "sonar")
        self._base_url = config.get("base_url", "https://api.perplexity.ai")

    def initialize(self) -> bool:
        if self._initialized:
            return True
        if not self._api_key:
            self._init_error = "Perplexity API key not configured"
            return False
        try:
            response = requests.get(
                f"{self._base_url}/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10,
            )
            if response.status_code != 200:
                self._init_error = f"Perplexity API returned status {response.status_code}"
                return False
            self._initialized = True
            return True
        except Exception as e:
            self._init_error = str(e)
            return False

    def chat(self, message: str, stream_callback: Optional[Callable[[str], None]] = None) -> str:
        if not self._initialized:
            if not self.initialize():
                return f"Error: {self._init_error}"
        try:
            if stream_callback:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": True},
                    stream=True, timeout=120,
                )
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if "choices" in data and data["choices"]:
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_response += content
                                stream_callback(content)
                return full_response
            else:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": False},
                    timeout=120,
                )
                if response.status_code != 200:
                    return f"Error: Perplexity API returned status {response.status_code}"
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Error: {str(e)}"


class OpenCodeZenProvider(BaseProvider):
    """OpenCode Zen provider."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("opencodezen", config)
        self._api_key = config.get("api_key", os.environ.get("OPENCODE_ZEN_API_KEY", ""))
        self._model = config.get("model", "opencode-zen")
        self._base_url = config.get("base_url", "https://api.opencode.ai/v1")

    def initialize(self) -> bool:
        if self._initialized:
            return True
        if not self._api_key:
            self._init_error = "OpenCode Zen API key not configured"
            return False
        try:
            response = requests.get(
                f"{self._base_url}/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10,
            )
            if response.status_code != 200:
                self._init_error = f"OpenCode Zen API returned status {response.status_code}"
                return False
            self._initialized = True
            return True
        except Exception as e:
            self._init_error = str(e)
            return False

    def chat(self, message: str, stream_callback: Optional[Callable[[str], None]] = None) -> str:
        if not self._initialized:
            if not self.initialize():
                return f"Error: {self._init_error}"
        try:
            if stream_callback:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": True},
                    stream=True, timeout=120,
                )
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if "choices" in data and data["choices"]:
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_response += content
                                stream_callback(content)
                return full_response
            else:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": False},
                    timeout=120,
                )
                if response.status_code != 200:
                    return f"Error: OpenCode Zen API returned status {response.status_code}"
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Error: {str(e)}"


class KimiProvider(BaseProvider):
    """Kimi / Moonshot provider."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("kimi", config)
        self._api_key = config.get("api_key", os.environ.get("KIMI_API_KEY", ""))
        self._model = config.get("model", "moonshot-v1-128k")
        self._base_url = config.get("base_url", "https://api.moonshot.ai/v1")

    def initialize(self) -> bool:
        if self._initialized:
            return True
        if not self._api_key:
            self._init_error = "Kimi API key not configured"
            return False
        try:
            response = requests.get(
                f"{self._base_url}/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10,
            )
            if response.status_code != 200:
                self._init_error = f"Kimi API returned status {response.status_code}"
                return False
            self._initialized = True
            return True
        except Exception as e:
            self._init_error = str(e)
            return False

    def chat(self, message: str, stream_callback: Optional[Callable[[str], None]] = None) -> str:
        if not self._initialized:
            if not self.initialize():
                return f"Error: {self._init_error}"
        try:
            if stream_callback:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": True},
                    stream=True, timeout=120,
                )
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if "choices" in data and data["choices"]:
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_response += content
                                stream_callback(content)
                return full_response
            else:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": False},
                    timeout=120,
                )
                if response.status_code != 200:
                    return f"Error: Kimi API returned status {response.status_code}"
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Error: {str(e)}"


class MiniMaxProvider(BaseProvider):
    """MiniMax provider."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("minimax", config)
        self._api_key = config.get("api_key", os.environ.get("MINIMAX_API_KEY", ""))
        self._model = config.get("model", "MiniMax-M1")
        self._base_url = config.get("base_url", "https://api.minimax.io/v1")

    def initialize(self) -> bool:
        if self._initialized:
            return True
        if not self._api_key:
            self._init_error = "MiniMax API key not configured"
            return False
        try:
            response = requests.get(
                f"{self._base_url}/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10,
            )
            if response.status_code != 200:
                self._init_error = f"MiniMax API returned status {response.status_code}"
                return False
            self._initialized = True
            return True
        except Exception as e:
            self._init_error = str(e)
            return False

    def chat(self, message: str, stream_callback: Optional[Callable[[str], None]] = None) -> str:
        if not self._initialized:
            if not self.initialize():
                return f"Error: {self._init_error}"
        try:
            if stream_callback:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": True},
                    stream=True, timeout=120,
                )
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if "choices" in data and data["choices"]:
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_response += content
                                stream_callback(content)
                return full_response
            else:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": False},
                    timeout=120,
                )
                if response.status_code != 200:
                    return f"Error: MiniMax API returned status {response.status_code}"
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Error: {str(e)}"


class ZAIProvider(BaseProvider):
    """Z.AI / GLM provider."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("zai", config)
        self._api_key = config.get("api_key", os.environ.get("GLM_API_KEY", ""))
        self._model = config.get("model", "glm-4-plus")
        self._base_url = config.get("base_url", "https://open.bigmodel.cn/api/paas/v4")

    def initialize(self) -> bool:
        if self._initialized:
            return True
        if not self._api_key:
            self._init_error = "Z.AI API key not configured"
            return False
        try:
            response = requests.get(
                f"{self._base_url}/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10,
            )
            if response.status_code != 200:
                self._init_error = f"Z.AI API returned status {response.status_code}"
                return False
            self._initialized = True
            return True
        except Exception as e:
            self._init_error = str(e)
            return False

    def chat(self, message: str, stream_callback: Optional[Callable[[str], None]] = None) -> str:
        if not self._initialized:
            if not self.initialize():
                return f"Error: {self._init_error}"
        try:
            if stream_callback:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": True},
                    stream=True, timeout=120,
                )
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if "choices" in data and data["choices"]:
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_response += content
                                stream_callback(content)
                return full_response
            else:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": False},
                    timeout=120,
                )
                if response.status_code != 200:
                    return f"Error: Z.AI API returned status {response.status_code}"
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Error: {str(e)}"



class NousResearchProvider(BaseProvider):
    """Nous Research provider (Hermes models via Nous Portal)."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("nous", config)
        self._api_key = config.get("api_key", os.environ.get("NOUS_API_KEY", ""))
        self._model = config.get("model", "Hermes-3-Llama-3.1-8B")
        self._base_url = config.get("base_url", "https://inference-api.nousresearch.com/v1")

    def initialize(self) -> bool:
        if self._initialized:
            return True
        if not self._api_key:
            self._init_error = "Nous API key not configured"
            return False
        try:
            response = requests.get(
                f"{self._base_url}/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10,
            )
            if response.status_code != 200:
                self._init_error = f"Nous API returned status {response.status_code}"
                return False
            self._initialized = True
            return True
        except Exception as e:
            self._init_error = str(e)
            return False

    def chat(self, message: str, stream_callback: Optional[Callable[[str], None]] = None) -> str:
        if not self._initialized:
            if not self.initialize():
                return f"Error: {self._init_error}"
        try:
            if stream_callback:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": True},
                    stream=True, timeout=120,
                )
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if "choices" in data and data["choices"]:
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_response += content
                                stream_callback(content)
                return full_response
            else:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": False},
                    timeout=120,
                )
                if response.status_code != 200:
                    return f"Error: Nous API returned status {response.status_code}"
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Error: {str(e)}"



class CustomProvider(BaseProvider):
    """Custom/OpenAI-compatible provider with user-specified URL."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("custom", config)
        self._api_key = config.get("api_key", "")
        self._model = config.get("model", "default")
        self._base_url = config.get("base_url", "")

    def initialize(self) -> bool:
        if self._initialized:
            return True
        if not self._base_url:
            self._init_error = "Custom provider URL not configured"
            return False
        try:
            response = requests.get(
                f"{self._base_url}/models",
                headers={"Authorization": f"Bearer {self._api_key}"} if self._api_key else {},
                timeout=10,
            )
            if response.status_code != 200:
                self._init_error = f"Custom API returned status {response.status_code}"
                return False
            self._initialized = True
            return True
        except Exception as e:
            self._init_error = str(e)
            return False

    def chat(self, message: str, stream_callback: Optional[Callable[[str], None]] = None) -> str:
        if not self._initialized:
            if not self.initialize():
                return f"Error: {self._init_error}"
        try:
            if stream_callback:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": True},
                    stream=True, timeout=120,
                )
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if "choices" in data and data["choices"]:
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_response += content
                                stream_callback(content)
                return full_response
            else:
                response = requests.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json={"model": self._model, "messages": [{"role": "user", "content": message}], "stream": False},
                    timeout=120,
                )
                if response.status_code != 200:
                    return f"Error: Custom API returned status {response.status_code}"
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Error: {str(e)}"


# Provider registry
PROVIDERS = {
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "copilot": CopilotProvider,
    "anthropic": AnthropicProvider,
    "openrouter": OpenRouterProvider,
    "groq": GroqProvider,
    "mistral": MistralProvider,
    "deepseek": DeepSeekProvider,
    "xai": XAIProvider,
    "together": TogetherProvider,
    "fireworks": FireworksProvider,
    "perplexity": PerplexityProvider,
    "opencodezen": OpenCodeZenProvider,
    "kimi": KimiProvider,
    "minimax": MiniMaxProvider,
    "zai": ZAIProvider,
    "nous": NousResearchProvider,
    "custom": CustomProvider,
}


class SaraAgent:
    """S.A.R.A Agent with multi-provider support."""

    def __init__(self):
        self._providers: Dict[str, BaseProvider] = {}
        self._active_provider: Optional[str] = None
        self._lock = threading.Lock()
        self._config: Dict[str, Any] = {}
        self._init_error: Optional[str] = None

    def load_config(self) -> Dict[str, Any]:
        """Load provider configuration from config.yaml."""
        try:
            import yaml
            config_path = SARA_ROOT / "config.yaml"
            if config_path.exists():
                with open(config_path) as f:
                    return yaml.safe_load(f) or {}
        except Exception:
            pass
        return {}

    def initialize(self, provider_name: Optional[str] = None) -> bool:
        """Initialize a specific provider or auto-detect."""
        with self._lock:
            self._config = self.load_config()

            # If no provider specified, try to auto-detect
            if provider_name is None:
                provider_name = self._config.get("provider", {}).get("active", "custom")

            # Create provider instance
            if provider_name not in PROVIDERS:
                return False

            # Get credentials from auth store
            from sara_auth_store import get_auth_store
            store = get_auth_store()
            store.load()

            cred = store.get_credential(provider_name)
            provider_config = self._config.get("providers", {}).get(provider_name, {})

            # Override with credential from store
            if cred and cred.api_key:
                provider_config["api_key"] = cred.api_key

            provider_class = PROVIDERS[provider_name]
            provider = provider_class(provider_config)

            if provider.initialize():
                self._providers[provider_name] = provider
                self._active_provider = provider_name
                return True

            return False

    def set_provider(self, provider_name: str, model: Optional[str] = None) -> bool:
        """Switch to a different provider."""
        if provider_name in self._providers:
            self._active_provider = provider_name
            if model:
                self._providers[provider_name]._model = model
            return True
        return self.initialize(provider_name)

    def chat(self, message: str, stream_callback: Optional[Callable[[str], None]] = None, model: Optional[str] = None) -> str:
        """Send a message through the active provider."""
        if self._active_provider is None:
            if not self.initialize():
                return "Error: No provider available"

        provider = self._providers.get(self._active_provider)
        if provider is None:
            return "Error: Provider not initialized"

        if model:
            provider._model = model

        return provider.chat(message, stream_callback)

    def is_ready(self) -> bool:
        """Check if the agent is initialized and ready."""
        return self._active_provider is not None

    def get_status(self) -> Dict[str, Any]:
        """Get status of all providers."""
        status = {
            "active_provider": self._active_provider,
            "providers": {},
        }
        for name, provider in self._providers.items():
            status["providers"][name] = provider.get_status()
        return status

    def list_providers(self) -> list:
        """List all available providers."""
        return list(PROVIDERS.keys())


# Global agent instance
_agent_instance: Optional[SaraAgent] = None
_agent_lock = threading.Lock()


def get_agent() -> SaraAgent:
    """Get or create the global agent instance."""
    global _agent_instance

    if _agent_instance is not None:
        return _agent_instance

    with _agent_lock:
        if _agent_instance is not None:
            return _agent_instance

        _agent_instance = SaraAgent()
        return _agent_instance


def process_message(message: str, stream_callback: Optional[Callable[[str], None]] = None) -> str:
    """Process a message through the active provider."""
    agent = get_agent()
    return agent.chat(message, stream_callback=stream_callback)
