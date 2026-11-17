"""Provider adapters. The only modules that know vendor wire formats."""

from jarvis.providers.adapters.anthropic import AnthropicAdapter
from jarvis.providers.adapters.gemini import GeminiAdapter
from jarvis.providers.adapters.ollama import OllamaAdapter
from jarvis.providers.adapters.openai_compat import OpenAICompatAdapter
from jarvis.providers.http import HttpAdapter

ADAPTERS: dict[str, type[HttpAdapter]] = {
    "anthropic": AnthropicAdapter,
    "openai": OpenAICompatAdapter,
    "gemini": GeminiAdapter,
    "ollama": OllamaAdapter,
}
