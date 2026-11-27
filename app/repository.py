"""DB 읽기/쓰기. 봇 핸들러와 LLM 비서가 모두 이 함수들을 씁니다."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Assignment, ClassSession, Exam, SentReminder


# ---------- 시간표 ----------
def add_class(s: Session, chat_id: int, course: str, weekday: int, start: time, end: time,
              location: str | None = None) -> ClassSession:
    row = ClassSession(chat_id=chat_id, course=course, weekday=weekday, start=start, end=end,
                       location=location)
    s.add(row)
    s.flush()
    return row


def list_classes(s: Session, chat_id: int, weekday: int | None = None) -> list[ClassSession]:
    q = select(ClassSession).where(ClassSession.chat_id == chat_id)
    if weekday is not None:
        q = q.where(ClassSession.weekday == weekday)
    return list(s.scalars(q.order_by(ClassSession.weekday, ClassSession.start)))


# ---------- 과제 ----------
def add_assignment(s: Session, chat_id: int, title: str, due_at: datetime,
                   course: str | None = None, note: str | None = None) -> Assignment:
    row = Assignment(chat_id=chat_id, title=title, due_at=due_at, course=course, note=note)
    s.add(row)
    s.flush()
    return row


def list_assignments(s: Session, chat_id: int, now: datetime, include_done: bool = False,
                     until: datetime | None = None) -> list[Assignment]:
    q = select(Assignment).where(Assignment.chat_id == chat_id, Assignment.due_at >= now)
    if not include_done:
        q = q.where(Assignment.done.is_(False))
    if until is not None:
        q = q.where(Assignment.due_at <= until)
    return list(s.scalars(q.order_by(Assignment.due_at)))


def mark_assignment_done(s: Session, chat_id: int, assignment_id: int) -> Assignment | None:
    row = s.get(Assignment, assignment_id)
    if row is None or row.chat_id != chat_id:
        return None
    row.done = True
    return row


# ---------- 시험 ----------
def add_exam(s: Session, chat_id: int, course: str, starts_at: datetime, title: str = "시험",
             location: str | None = None) -> Exam:
    row = Exam(chat_id=chat_id, course=course, starts_at=starts_at, title=title, location=location)
    s.add(row)
    s.flush()
    return row


def list_exams(s: Session, chat_id: int, now: datetime, until: datetime | None = None) -> list[Exam]:
    q = select(Exam).where(Exam.chat_id == chat_id, Exam.starts_at >= now)
    if until is not None:
        q = q.where(Exam.starts_at <= until)
    return list(s.scalars(q.order_by(Exam.starts_at)))


# ---------- 삭제 ----------
MODELS = {"class": ClassSession, "hw": Assignment, "exam": Exam}


def delete_item(s: Session, chat_id: int, kind: str, item_id: int) -> bool:
    model = MODELS.get(kind)
    if model is None:
        return False
    row = s.get(model, item_id)
    if row is None or row.chat_id != chat_id:
        return False
    s.delete(row)
    return True


# ---------- 알림 ----------
def due_reminders(s: Session, now: datetime, assignment_hours: list[int], exam_hours: list[int]):
    """지금 보내야 할 알림 목록: (kind, item, hours_before)."""
    sent = {(r.kind, r.item_id, r.hours_before) for r in s.scalars(select(SentReminder))}
    out = []
    horizon_a = now + timedelta(hours=max(assignment_hours, default=0))
    for a in s.scalars(select(Assignment).where(Assignment.done.is_(False),
                                                Assignment.due_at > now,
                                                Assignment.due_at <= horizon_a)):
        h = _pick_window(a.due_at - now, assignment_hours)
        if h is not None and ("assignment", a.id, h) not in sent:
            out.append(("assignment", a, h))
    horizon_e = now + timedelta(hours=max(exam_hours, default=0))
    for e in s.scalars(select(Exam).where(Exam.starts_at > now, Exam.starts_at <= horizon_e)):
        h = _pick_window(e.starts_at - now, exam_hours)
        if h is not None and ("exam", e.id, h) not in sent:
            out.append(("exam", e, h))
    return out


def _pick_window(remaining: timedelta, hours: list[int]) -> int | None:
    """남은 시간이 들어가는 가장 작은 알림 구간 (예: 남은 2시간 → 3시간 전 알림)."""
    fits = [h for h in hours if remaining <= timedelta(hours=h)]
    return min(fits) if fits else None


def record_reminder(s: Session, kind: str, item_id: int, hours_before: int, now: datetime) -> None:
    s.add(SentReminder(kind=kind, item_id=item_id, hours_before=hours_before, sent_at=now))


def mark_older_windows_sent(s: Session, kind: str, item_id: int, hours_before: int,
                            all_hours: list[int], now: datetime) -> None:
    """3시간 전 알림을 보냈다면 24시간 전 알림은 이제 의미 없으니 같이 기록."""
    existing = {r.hours_before for r in s.scalars(
        select(SentReminder).where(SentReminder.kind == kind, SentReminder.item_id == item_id))}
    for h in all_hours:
        if h > hours_before and h not in existing:
            record_reminder(s, kind, item_id, h, now)


def day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time.min)
    return start, start + timedelta(days=1)
