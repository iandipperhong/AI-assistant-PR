from __future__ import annotations

import httpx

from app.llm.base import LLMError, LLMProvider


class OllamaProvider(LLMProvider):
    """로컬 모델 (Ollama). 서버에 GPU가 있거나 작은 모델을 쓸 때."""

    name = "ollama"

    def __init__(self, base_url: str, model: str):
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def generate(self, system: str, prompt: str, *, json_mode: bool = False) -> str:
        payload = {
            "model": self._model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        if json_mode:
            payload["format"] = "json"
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(f"{self._base_url}/api/chat", json=payload)
                r.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama 호출 실패: {exc}") from exc
        return r.json().get("message", {}).get("content", "")
