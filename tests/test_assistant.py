import json
from datetime import datetime, timedelta

import pytest

from app import repository as repo
from app.assistant import build_context, handle_message
from app.llm.base import LLMError, LLMProvider

NOW = datetime(2026, 11, 27, 12, 0)


class FakeLLM(LLMProvider):
    def __init__(self, response=None, error=False):
        self.response, self.error, self.prompts = response, error, []

    async def generate(self, system, prompt, *, json_mode=False):
        self.prompts.append(prompt)
        if self.error:
            raise LLMError("boom")
        return self.response


def test_context_contains_items(session):
    repo.add_assignment(session, 1, "과제3", NOW + timedelta(days=1), course="자료구조")
    repo.add_assignment(session, 2, "남의 과제", NOW + timedelta(days=1))
    ctx = build_context(session, 1, NOW)
    assert "과제3" in ctx and "남의 과제" not in ctx and "금요일" in ctx


@pytest.mark.asyncio
async def test_answer_passthrough(session):
    llm = FakeLLM(json.dumps({"action": "answer", "reply": "내일은 과제3 마감이에요"}))
    assert await handle_message(llm, session, 1, "내일 과제 뭐 있어?", NOW) == "내일은 과제3 마감이에요"


@pytest.mark.asyncio
async def test_add_assignment_via_llm(session):
    llm = FakeLLM(json.dumps({"action": "add_assignment", "reply": "",
                              "data": {"title": "과제2", "course": "운영체제", "due": "2026-12-04 23:59"}}))
    reply = await handle_message(llm, session, 1, "금요일까지 운영체제 과제2 등록해줘", NOW)
    assert "등록했어요" in reply
    rows = repo.list_assignments(session, 1, NOW)
    assert rows[0].title == "과제2" and rows[0].due_at == datetime(2026, 12, 4, 23, 59)


@pytest.mark.asyncio
async def test_bad_payload_and_llm_error(session):
    bad = FakeLLM(json.dumps({"action": "add_exam", "data": {"course": "OS"}}))
    assert "명령어로" in await handle_message(bad, session, 1, "시험 등록", NOW)
    assert "AI 응답" in await handle_message(FakeLLM(error=True), session, 1, "안녕", NOW)


def test_explain_llm_error():
    from app.llm.base import explain_llm_error

    assert "키가 틀렸" in explain_llm_error(Exception("400 INVALID_ARGUMENT. API key not valid. Please pass a valid API key."))
    assert "한도" in explain_llm_error(Exception("429 RESOURCE_EXHAUSTED"))
    assert "모델 이름" in explain_llm_error(Exception("404 NOT_FOUND. models/gemini-x is not found"))
    assert "지역" in explain_llm_error(Exception("400 FAILED_PRECONDITION. User location is not supported"))
    assert "AIza" not in explain_llm_error(Exception("weird AIzaSyABCDEFGHIJKLMNOP error"))


@pytest.mark.asyncio
async def test_memory_guidelines_and_identity(session):
    llm = FakeLLM(json.dumps({"action": "save_guideline", "reply": "응 알겠어!", "data": {"text": "반말로 말하기"}}))
    reply = await handle_message(llm, session, 1, "앞으로 반말로 해줘", NOW)
    assert "지침 #" in reply and "반말로 말하기" in reply

    llm2 = FakeLLM(json.dumps({"action": "answer", "reply": "응, 나 기억해"}))
    await handle_message(llm2, session, 1, "내 말 기억해?", NOW)
    prompt = llm2.prompts[0]
    # 지침과 앞 대화가 같이 들어감, 다른 사용자 것은 안 들어감
    assert "반말로 말하기" in prompt and "앞으로 반말로 해줘" in prompt
    await handle_message(FakeLLM(json.dumps({"action": "answer", "reply": "x"})), session, 2, "남의 대화", NOW)
    llm3 = FakeLLM(json.dumps({"action": "answer", "reply": "ok"}))
    await handle_message(llm3, session, 1, "다시", NOW)
    assert "남의 대화" not in llm3.prompts[0]

    gid = repo.list_guidelines(session, 1)[0].id
    out = await handle_message(FakeLLM(json.dumps({"action": "delete_guideline", "reply": "지웠어", "data": {"id": gid}})),
                               session, 1, "지침 지워", NOW)
    assert out == "지웠어" and repo.list_guidelines(session, 1) == []


def test_system_prompt_names_model():
    from app.assistant import SYSTEM_PROMPT
    assert "Google Gemini (gemini-3.5-flash-lite)" in SYSTEM_PROMPT.format(model="Google Gemini (gemini-3.5-flash-lite)")


def test_chat_history_is_trimmed(session):
    for i in range(50):
        repo.add_chat(session, 1, "user", f"m{i}", NOW, keep=40)
    rows = repo.recent_chat(session, 1, 100)
    assert len(rows) == 40 and rows[0].text == "m10" and rows[-1].text == "m49"


def test_guideline_commands():
    from app.bot import commands as cmd
    assert "지침 #" in cmd.guideline_add(9, "존댓말 금지")
    assert "존댓말 금지" in cmd.guidelines_text(9)
    assert "찾지 못했어요" in cmd.guideline_delete(8, [1])
    assert "1개를 지웠어요" in cmd.guideline_delete(9, [1])
    assert "지웠어요" in cmd.chat_clear(9)
