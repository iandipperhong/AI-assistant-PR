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

    def describe(self) -> str:
        """'너 무슨 AI야?' 에 답할 때 쓰는 이름."""
        return self.name

    @abstractmethod
    async def generate(self, system: str, prompt: str, *, json_mode: bool = False) -> str:
        """system 지시문과 사용자 prompt 를 받아 텍스트(또는 JSON 문자열)를 돌려줍니다."""


def explain_llm_error(exc: Exception) -> str:
    """LLM 오류를 사용자가 고칠 수 있는 한 줄 설명으로 (서버 로그를 안 봐도 원인을 알 수 있게)."""
    import re

    text = str(exc)
    low = text.lower()
    if "비어 있어요" in text:
        return "API 키가 서버에 없어요. GitHub Secret 을 등록하고 다시 배포하세요."
    if "api key" in low or "api_key" in low or "permission_denied" in low or " 401" in low or " 403" in low:
        return "API 키가 틀렸거나 막혔어요. 키를 새로 발급해 GitHub Secret 을 바꾸고 다시 배포하세요."
    if "429" in low or "resource_exhausted" in low or "quota" in low:
        return "무료 사용 한도를 넘었어요. 잠시(또는 내일) 뒤에 다시 해 보세요."
    if "location" in low or "region" in low or "failed_precondition" in low:
        return "이 서버 지역에서는 이 AI 를 쓸 수 없어요."
    if "404" in low or "not found" in low or "is not supported" in low:
        return "AI 모델 이름이 더 이상 쓰이지 않아요. GEMINI_MODEL 설정을 바꿔야 해요."
    if "timeout" in low or "timed out" in low or "connect" in low:
        return "AI 서버에 연결하지 못했어요. 잠시 뒤 다시 해 보세요."
    short = re.sub(r"AIza[0-9A-Za-z_\-]{10,}", "***", text)  # 혹시 키가 섞여 있으면 가림
    return f"오류 내용: {short[:200]}"
