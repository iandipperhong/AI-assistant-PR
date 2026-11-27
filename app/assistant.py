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
from app.config import settings
from app.llm.base import LLMError, LLMProvider, explain_llm_error
from app.models import WEEKDAYS
from app.parsing import ParseError, parse_time_range, parse_weekday

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """너는 서울시립대학교 조경학과 학생의 대학생활 비서 디스코드 봇이야. 한국어로 짧고 친근하게 답해.
너는 {model} 언어모델로 돌아가. 무슨 AI/모델이냐고 물으면 숨기지 말고 그대로 말해.

아래에 [사용자 지침], [최근 대화], 사용자의 시간표·과제·시험 목록이 주어진다.
- [사용자 지침]은 항상 지켜 (말투, 호칭 등).
- [최근 대화]로 앞에서 한 얘기를 이어가. 같은 걸 다시 묻지 마.
- 일정 질문은 목록만 근거로 답하고, 목록에 없는 일정은 지어내지 마. 그 밖의 잡담·일반 질문은 자유롭게 답해.

반드시 다음 JSON 하나만 출력해:
{{
  "action": "answer" | "add_assignment" | "add_exam" | "add_class" | "save_guideline" | "delete_guideline",
  "reply": "사용자에게 보낼 한국어 문장",
  "data": {{ ... }}   // answer 가 아닐 때만
}}
- add_assignment data: {{"title": str, "course": str|null, "due": "YYYY-MM-DD HH:MM"}}  (시간 언급 없으면 23:59)
- add_exam data: {{"course": str, "title": str, "starts": "YYYY-MM-DD HH:MM", "location": str|null}}
- add_class data: {{"course": str, "weekday": "월"~"일", "time": "HH:MM-HH:MM", "location": str|null}}
- save_guideline data: {{"text": "앞으로 지킬 지침 한 문장"}}  (사용자가 "앞으로 ~해줘", "지침/규칙으로 저장해" 처럼 계속 지킬 것을 요청할 때)
- delete_guideline data: {{"id": 번호}}  ([사용자 지침]의 #번호)
사용자가 명확히 요청했을 때만 answer 이외의 action 을 써.
"""


def build_context(s: Session, user_id: int, now: datetime) -> str:
    lines = [f"현재 시각: {now:%Y-%m-%d %H:%M} ({WEEKDAYS[now.weekday()]}요일)", "", "[사용자 지침]"]
    lines += [f"- #{g.id} {g.text}" for g in repo.list_guidelines(s, user_id)] or ["- (없음)"]
    lines += ["", "[최근 대화] (오래된 것부터)"]
    history = repo.recent_chat(s, user_id, settings.chat_context_messages)
    lines += [f"{'사용자' if m.role == 'user' else '봇'}: {m.text[:500]}" for m in history] or ["(없음)"]
    lines += ["", "[시간표]"]
    classes = repo.list_classes(s, user_id)
    lines += [f"- {c.describe()}" for c in classes] or ["- (없음)"]
    lines += ["", "[다가오는 과제 (30일)]"]
    hws = repo.list_assignments(s, user_id, now, until=now + timedelta(days=30))
    lines += [f"- {a.describe()}" for a in hws] or ["- (없음)"]
    lines += ["", "[다가오는 시험 (60일)]"]
    exams = repo.list_exams(s, user_id, now, until=now + timedelta(days=60))
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


async def handle_message(llm: LLMProvider, s: Session, user_id: int, text: str, now: datetime) -> str:
    reply = await _respond(llm, s, user_id, text, now)
    repo.add_chat(s, user_id, "user", text, now, settings.chat_history_limit)
    repo.add_chat(s, user_id, "bot", reply, now, settings.chat_history_limit)
    return reply


async def _respond(llm: LLMProvider, s: Session, user_id: int, text: str, now: datetime) -> str:
    prompt = f"{build_context(s, user_id, now)}\n\n[사용자 메시지]\n{text}"
    try:
        raw = await llm.generate(SYSTEM_PROMPT.format(model=llm.describe()), prompt, json_mode=True)
    except LLMError as exc:
        log.warning("LLM error: %s", exc)
        return (f"지금은 AI 응답을 받을 수 없어요. `/help` 의 명령어로는 계속 쓸 수 있어요.\n"
                f"원인: {explain_llm_error(exc)}")

    try:
        result = _extract_json(raw)
    except (ValueError, json.JSONDecodeError):
        return raw.strip() or "음, 잘 이해하지 못했어요."

    action = result.get("action", "answer")
    reply = str(result.get("reply", "")).strip()
    data = result.get("data") or {}

    try:
        if action == "add_assignment":
            row = repo.add_assignment(s, user_id, title=data["title"], due_at=_parse_dt(data["due"]),
                                      course=data.get("course"))
            return f"과제를 등록했어요: {row.describe()}\n잘못됐으면 `/del` 과제 {row.id}"
        if action == "add_exam":
            row = repo.add_exam(s, user_id, course=data["course"], starts_at=_parse_dt(data["starts"]),
                                title=data.get("title") or "시험", location=data.get("location"))
            return f"시험을 등록했어요: {row.describe()}\n잘못됐으면 `/del` 시험 {row.id}"
        if action == "add_class":
            start, end = parse_time_range(data["time"])
            row = repo.add_class(s, user_id, course=data["course"], weekday=parse_weekday(data["weekday"]),
                                 start=start, end=end, location=data.get("location"))
            return f"시간표에 추가했어요: {row.describe()}\n잘못됐으면 `/del` 수업 {row.id}"
        if action == "save_guideline":
            g_text = str(data["text"]).strip()
            if not g_text:
                raise ValueError("빈 지침")
            if len(repo.list_guidelines(s, user_id)) >= settings.max_guidelines:
                return f"지침은 {settings.max_guidelines}개까지 저장돼요. 대시보드 🧠 지침에서 안 쓰는 걸 지워 주세요."
            row = repo.add_guideline(s, user_id, g_text, now)
            return f"{reply or '알겠어요!'}\n📌 지침 #{row.id} 저장: {row.text}"
        if action == "delete_guideline":
            ok = repo.delete_guideline(s, user_id, int(data["id"]))
            return (reply or "지침을 지웠어요.") if ok else "그 번호의 지침을 찾지 못했어요."
    except (KeyError, ValueError, TypeError, ParseError) as exc:
        log.info("LLM add payload invalid: %s / %s", exc, data)
        return "요청을 정확히 못 읽었어요. 명령어로 해 주세요 (`/help`)."

    return reply or "음, 잘 이해하지 못했어요."


__all__ = ["handle_message", "build_context"]
