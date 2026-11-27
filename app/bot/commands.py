"""슬래시 명령어의 실제 동작. 디스코드와 무관한 순수 함수라 테스트하기 쉽습니다.

각 함수는 (user_id, 인자...) 를 받아 답장 문자열을 돌려줍니다.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app import repository as repo
from app.bot import formatting as fmt
from app.clock import now
from app.db import session_scope
from app.parsing import ParseError, parse_date, parse_time, parse_time_range, parse_weekday

HELP = """**서울시립대 생활 비서** 🤖

**등록**
`/class_add` 요일·시간(09:00-10:15)·과목·장소
`/hw_add` 날짜·과목·제목·시간(생략 시 23:59)
`/exam_add` 날짜·시간·과목·시험이름·장소
날짜는 `12/03`, `2026-12-03`, `오늘`, `내일`, `모레` 모두 가능

**조회**
`/today` `/tomorrow` `/week` `/hw` `/exams` `/timetable`

**관리**
`/done` 과제 완료 · `/del` 항목 삭제

그냥 말로 해도 돼요 (DM이나 @멘션): "내일 과제 뭐 있어?", "금요일까지 운영체제 과제2 등록해줘"
"""


def class_add(user_id: int, weekday: str, time_range: str, course: str, location: str | None) -> str:
    wd = parse_weekday(weekday)
    start, end = parse_time_range(time_range)
    with session_scope() as s:
        row = repo.add_class(s, user_id, course.strip(), wd, start, end, location or None)
        return f"시간표에 추가했어요: #{row.id} {row.describe()}"


def hw_add(user_id: int, date: str, course: str | None, title: str, at: str | None) -> str:
    n = now()
    due = datetime.combine(parse_date(date, n.date()), parse_time(at or "23:59"))
    with session_scope() as s:
        row = repo.add_assignment(s, user_id, title=title.strip(), due_at=due, course=course or None)
        return f"과제를 등록했어요: {row.describe()}"


def exam_add(user_id: int, date: str, at: str, course: str, title: str | None, location: str | None) -> str:
    n = now()
    starts = datetime.combine(parse_date(date, n.date()), parse_time(at))
    with session_scope() as s:
        row = repo.add_exam(s, user_id, course.strip(), starts, title or "시험", location or None)
        return f"시험을 등록했어요: {row.describe()}"


def day(user_id: int, offset_days: int) -> str:
    n = now()
    with session_scope() as s:
        return fmt.day_summary(s, user_id, n.date() + timedelta(days=offset_days), n)


def week(user_id: int) -> str:
    with session_scope() as s:
        return fmt.week_text(s, user_id, now())


def hw_list(user_id: int) -> str:
    with session_scope() as s:
        return fmt.assignments_text(s, user_id, now())


def exams(user_id: int) -> str:
    with session_scope() as s:
        return fmt.exams_text(s, user_id, now())


def timetable(user_id: int) -> str:
    with session_scope() as s:
        return fmt.timetable_text(s, user_id)


def done(user_id: int, assignment_id: int) -> str:
    with session_scope() as s:
        row = repo.mark_assignment_done(s, user_id, assignment_id)
        return f"수고했어요! {row.describe()}" if row else "그 번호의 과제를 찾지 못했어요."


def delete(user_id: int, kind: str, item_id: int) -> str:
    if kind not in repo.MODELS:
        raise ParseError("종류는 class, hw, exam 중 하나예요")
    with session_scope() as s:
        ok = repo.delete_item(s, user_id, kind, item_id)
    return "삭제했어요." if ok else "그 항목을 찾지 못했어요."
