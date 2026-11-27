"""LLM 추상화 계층.

봇 코드는 이 인터페이스만 알고, 실제 모델(Gemini/Claude/Ollama)은 LLM_PROVIDER 로 고릅니다.
새 모델을 붙이려면 LLMProvider 를 상속해 generate() 하나만 구현하면 됩니다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class LLMError(RuntimeError):
    pass


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def generate(self, system: str, prompt: str, *, json_mode: bool = False) -> str:
        """system 지시문과 사용자 prompt 를 받아 텍스트(또는 JSON 문자열)를 돌려줍니다."""
