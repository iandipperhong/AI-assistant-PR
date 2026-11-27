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
