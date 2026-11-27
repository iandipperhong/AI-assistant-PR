from __future__ import annotations

from functools import lru_cache

from app.config import settings
from app.llm.base import LLMError, LLMProvider


@lru_cache(maxsize=1)
def get_llm() -> LLMProvider:
    provider = settings.llm_provider
    if provider == "gemini":
        from app.llm.gemini import GeminiProvider

        return GeminiProvider(settings.gemini_api_key, settings.gemini_model)
    if provider == "claude":
        from app.llm.claude import ClaudeProvider

        return ClaudeProvider(settings.anthropic_api_key, settings.claude_model)
    if provider == "ollama":
        from app.llm.ollama import OllamaProvider

        return OllamaProvider(settings.ollama_base_url, settings.ollama_model)
    raise LLMError(f"알 수 없는 LLM_PROVIDER: {provider}")
