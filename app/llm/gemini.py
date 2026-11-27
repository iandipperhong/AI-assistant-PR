from __future__ import annotations

from app.llm.base import LLMError, LLMProvider


class GeminiProvider(LLMProvider):
    """Google Gemini API (무료 티어로 시작)."""

    name = "gemini"

    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise LLMError("GEMINI_API_KEY 가 비어 있어요")
        from google import genai  # 선택 의존성: 다른 공급자만 쓸 땐 import 안 함

        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def generate(self, system: str, prompt: str, *, json_mode: bool = False) -> str:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json" if json_mode else "text/plain",
            temperature=0.3,
        )
        try:
            resp = await self._client.aio.models.generate_content(
                model=self._model, contents=prompt, config=config
            )
        except Exception as exc:  # 네트워크/쿼터 오류 등
            raise LLMError(f"Gemini 호출 실패: {exc}") from exc
        return resp.text or ""
