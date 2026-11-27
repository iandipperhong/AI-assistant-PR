from __future__ import annotations

import logging

from app.llm.base import LLMError, LLMProvider

log = logging.getLogger(__name__)

# 설정한 모델이 없어졌거나(404) 무료로 못 쓰면(429) 차례로 시도할 모델 (2026-11 기준 Google 문서)
# - gemini-2.5-flash: 예전부터 쓰던 프로젝트만 사용 가능, 새 키에서는 404
# - gemini-3.1-flash-lite: 무료 티어 확인됨, 2027-05-07 종료 예정
FALLBACK_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-latest")


def _should_try_next(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(k in text for k in ("404", "not found", "not_found", "is not supported", "429", "resource_exhausted"))


class GeminiProvider(LLMProvider):
    """Google Gemini API (무료 티어로 시작). 모델이 사라지면 다음 후보로 자동 전환."""

    name = "gemini"

    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise LLMError("GEMINI_API_KEY 가 비어 있어요")
        from google import genai  # 선택 의존성: 다른 공급자만 쓸 땐 import 안 함

        self._client = genai.Client(api_key=api_key)
        self._models = [model] + [m for m in FALLBACK_MODELS if m != model]

    async def _call(self, model: str, system: str, prompt: str, json_mode: bool) -> str:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json" if json_mode else "text/plain",
            temperature=0.3,
        )
        resp = await self._client.aio.models.generate_content(model=model, contents=prompt, config=config)
        return resp.text or ""

    async def generate(self, system: str, prompt: str, *, json_mode: bool = False) -> str:
        last: Exception | None = None
        for i, model in enumerate(list(self._models)):
            try:
                text = await self._call(model, system, prompt, json_mode)
            except Exception as exc:  # 네트워크/쿼터/모델 오류 등
                last = exc
                if _should_try_next(exc) and i + 1 < len(self._models):
                    log.warning("Gemini 모델 %s 실패, 다음 후보로: %s", model, str(exc)[:200])
                    continue
                break
            if i:  # 잘 되는 모델을 맨 앞으로 (다음부터 바로 사용)
                self._models.remove(model)
                self._models.insert(0, model)
                log.info("Gemini 모델을 %s 로 전환", model)
            return text
        raise LLMError(f"Gemini 호출 실패: {last}") from last
