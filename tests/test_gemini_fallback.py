import pytest

from app.llm.base import LLMError
from app.llm.gemini import GeminiProvider


def _provider(model, fails):
    p = GeminiProvider.__new__(GeminiProvider)  # 실제 API 없이
    p._models = [model] + [m for m in ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-latest")
                           if m != model]
    p.calls = []

    async def fake_call(m, system, prompt, json_mode):
        p.calls.append(m)
        if m in fails:
            raise Exception(fails[m])
        return f"ok:{m}"

    p._call = fake_call
    return p


@pytest.mark.asyncio
async def test_falls_back_on_404_and_remembers():
    p = _provider("gemini-2.5-flash", {"gemini-2.5-flash": "404 NOT_FOUND",
                                        "gemini-3.5-flash-lite": "429 RESOURCE_EXHAUSTED limit: 0"})
    assert await p.generate("s", "q") == "ok:gemini-3.1-flash-lite"
    p.calls.clear()
    assert await p.generate("s", "q") == "ok:gemini-3.1-flash-lite"
    assert p.calls == ["gemini-3.1-flash-lite"]


@pytest.mark.asyncio
async def test_bad_key_does_not_fall_back():
    p = _provider("gemini-3.5-flash-lite", {"gemini-3.5-flash-lite": "400 API key not valid"})
    with pytest.raises(LLMError):
        await p.generate("s", "q")
    assert p.calls == ["gemini-3.5-flash-lite"]
