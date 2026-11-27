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

**버튼 대시보드**: #대시보드 채널의 고정 메시지 (학식·공지·학사일정·과제·졸업요건)

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


# ---------- 졸업요건 ----------
def grad_summary(user_id: int) -> str:
    from app import graduation

    with session_scope() as s:
        return graduation.summary(repo.list_completed_courses(s, user_id))


def grad_add(user_id: int, name: str, credits: str | None, category: str | None) -> str:
    from app.campus import landscape_curriculum as cur

    name = name.strip()
    if not name:
        raise ParseError("과목 이름을 적어 주세요")
    known = cur.find_course(name)
    raw = (credits or "").strip() or str(known.credits if known else cur.DEFAULT_CREDITS)
    if not raw.isdigit() or not 0 <= int(raw) <= 9:
        raise ParseError("학점은 0~9 사이 숫자로 적어 주세요")
    category = _pick_category(category, name)
    with session_scope() as s:
        row = repo.add_completed_course(s, user_id, name, int(raw), category)
        return f"추가했어요: #{row.id} {row.name} ({row.category}, {row.credits}학점)"


def grad_quick_add(user_id: int, names: list[str]) -> str:
    """전공 과목 목록에서 고른 과목을 한꺼번에 추가 (학점은 기본값, 이미 있는 과목은 건너뜀)."""
    from app.campus import landscape_curriculum as cur

    with session_scope() as s:
        have = {cur.normalize(c.name) for c in repo.list_completed_courses(s, user_id)}
        added = []
        for name in names:
            if cur.normalize(name) in have:
                continue
            known = cur.find_course(name)
            repo.add_completed_course(s, user_id, known.name if known else name,
                                      known.credits if known else cur.DEFAULT_CREDITS, _pick_category(None, name))
            have.add(cur.normalize(name))
            added.append(name)
    if not added:
        return "이미 다 들어 있어요."
    return f"{len(added)}과목 추가했어요: {', '.join(added)}\n(학점·구분은 2026 교과과정 기준으로 넣었어요)"


def grad_delete(user_id: int, course_ids: list[int]) -> str:
    with session_scope() as s:
        n = sum(repo.delete_completed_course(s, user_id, cid) for cid in course_ids)
    return f"{n}과목 삭제했어요." if n else "삭제할 과목을 찾지 못했어요."


def _pick_category(category: str | None, name: str) -> str:
    from app.campus import landscape_curriculum as cur

    category = (category or "").strip().replace(" ", "")
    if not category:
        known = cur.find_course(name)
        return known.category if known else "교양선택"
    aliases = {"전필": "전공필수", "전선": "전공선택", "교필": "교양필수", "교선": "교양선택", "일선": "일반선택"}
    category = aliases.get(category, category)
    if category not in cur.CATEGORIES:
        raise ParseError(f"구분은 {', '.join(cur.CATEGORIES)} 중 하나로 적어 주세요 (전필/전선/교필/교선도 돼요)")
    return category
