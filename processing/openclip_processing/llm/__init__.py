"""Pluggable AI providers. Every provider returns JSON that matches a given schema."""

from openclip_processing.llm.base import LLMProvider, extract_json
from openclip_processing.llm.ollama import OllamaProvider
from openclip_processing.llm.openai_compat import OpenAICompatibleProvider

__all__ = ["LLMProvider", "OllamaProvider", "OpenAICompatibleProvider", "extract_json"]
