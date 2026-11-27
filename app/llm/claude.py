from __future__ import annotations

import httpx

from app.llm.base import LLMError, LLMProvider


class ClaudeProvider(LLMProvider):
    """Anthropic Claude (Messages API). 나중에 교체용."""

    name = "claude"
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY 가 비어 있어요")
        self._api_key = api_key
        self._model = model

    async def generate(self, system: str, prompt: str, *, json_mode: bool = False) -> str:
        if json_mode:
            system += "\n\n반드시 JSON 객체 하나만 출력하세요. 다른 글자는 쓰지 마세요."
        payload = {
            "model": self._model,
            "max_tokens": 1024,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {"x-api-key": self._api_key, "anthropic-version": "2023-06-01"}
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(self.URL, json=payload, headers=headers)
                r.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Claude 호출 실패: {exc}") from exc
        return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
