"""자연어 대화 처리: "내일 과제 뭐 있어?", "금요일까지 자료구조 과제3 등록해줘" 같은 말.

흐름: DB에서 사용자의 일정을 모아 컨텍스트로 넣고 → LLM 이 JSON으로 행동을 고름 →
등록 요청이면 여기서 검증 후 DB에 저장, 질문이면 LLM 답을 그대로 돌려줌.
LLM 은 DB 를 직접 건드리지 않습니다.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import repository as repo
from app.llm.base import LLMError, LLMProvider
from app.models import WEEKDAYS
from app.parsing import ParseError, parse_time_range, parse_weekday

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """너는 서울시립대학교 학생의 대학생활 비서야. 한국어로 짧고 친근하게 답해.
아래에 사용자의 시간표, 다가오는 과제, 시험 목록이 주어진다. 이 정보만 근거로 답하고,
목록에 없는 일정은 지어내지 마. 모르면 모른다고 말해.

반드시 다음 JSON 하나만 출력해:
{
  "action": "answer" | "add_assignment" | "add_exam" | "add_class",
  "reply": "사용자에게 보낼 한국어 문장",
  "data": { ... }   // add_* 일 때만
}
- add_assignment data: {"title": str, "course": str|null, "due": "YYYY-MM-DD HH:MM"}  (시간 언급 없으면 23:59)
- add_exam data: {"course": str, "title": str, "starts": "YYYY-MM-DD HH:MM", "location": str|null}
- add_class data: {"course": str, "weekday": "월"~"일", "time": "HH:MM-HH:MM", "location": str|null}
사용자가 등록을 명확히 요청했을 때만 add_* 를 쓰고, 그 외엔 answer 를 써.
"""


def build_context(s: Session, chat_id: int, now: datetime) -> str:
    lines = [f"현재 시각: {now:%Y-%m-%d %H:%M} ({WEEKDAYS[now.weekday()]}요일)", "", "[시간표]"]
    classes = repo.list_classes(s, chat_id)
    lines += [f"- {c.describe()}" for c in classes] or ["- (없음)"]
    lines += ["", "[다가오는 과제 (30일)]"]
    hws = repo.list_assignments(s, chat_id, now, until=now + timedelta(days=30))
    lines += [f"- {a.describe()}" for a in hws] or ["- (없음)"]
    lines += ["", "[다가오는 시험 (60일)]"]
    exams = repo.list_exams(s, chat_id, now, until=now + timedelta(days=60))
    lines += [f"- {e.describe()}" for e in exams] or ["- (없음)"]
    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("JSON 없음")
    return json.loads(m.group(0))


def _parse_dt(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%Y-%m-%d %H:%M")


async def handle_message(llm: LLMProvider, s: Session, chat_id: int, text: str, now: datetime) -> str:
    prompt = f"{build_context(s, chat_id, now)}\n\n[사용자 메시지]\n{text}"
    try:
        raw = await llm.generate(SYSTEM_PROMPT, prompt, json_mode=True)
    except LLMError as exc:
        log.warning("LLM error: %s", exc)
        return "지금은 AI 응답을 받을 수 없어요. /help 의 명령어로는 계속 쓸 수 있어요."

    try:
        result = _extract_json(raw)
    except (ValueError, json.JSONDecodeError):
        return raw.strip() or "음, 잘 이해하지 못했어요."

    action = result.get("action", "answer")
    reply = str(result.get("reply", "")).strip()
    data = result.get("data") or {}

    try:
        if action == "add_assignment":
            row = repo.add_assignment(s, chat_id, title=data["title"], due_at=_parse_dt(data["due"]),
                                      course=data.get("course"))
            return f"과제를 등록했어요: {row.describe()}\n잘못됐으면 /del hw {row.id}"
        if action == "add_exam":
            row = repo.add_exam(s, chat_id, course=data["course"], starts_at=_parse_dt(data["starts"]),
                                title=data.get("title") or "시험", location=data.get("location"))
            return f"시험을 등록했어요: {row.describe()}\n잘못됐으면 /del exam {row.id}"
        if action == "add_class":
            start, end = parse_time_range(data["time"])
            row = repo.add_class(s, chat_id, course=data["course"], weekday=parse_weekday(data["weekday"]),
                                 start=start, end=end, location=data.get("location"))
            return f"시간표에 추가했어요: {row.describe()}\n잘못됐으면 /del class {row.id}"
    except (KeyError, ValueError, ParseError) as exc:
        log.info("LLM add payload invalid: %s / %s", exc, data)
        return "등록하려는 내용을 정확히 못 읽었어요. 명령어로 등록해 주세요 (/help)."

    return reply or "음, 잘 이해하지 못했어요."


__all__ = ["handle_message", "build_context"]
