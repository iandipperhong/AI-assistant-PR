"""목록을 디스코드 메시지로 바꾸는 함수들 (테스트하기 쉽게 핸들러와 분리)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app import repository as repo
from app.models import WEEKDAYS


def day_summary(s: Session, user_id: int, d: date, now: datetime) -> str:
    start, end = repo.day_bounds(d)
    label = f"{d:%m/%d} ({WEEKDAYS[d.weekday()]})"
    classes = repo.list_classes(s, user_id, weekday=d.weekday())
    hws = [a for a in repo.list_assignments(s, user_id, max(now, start), until=end)]
    exams = repo.list_exams(s, user_id, max(now, start), until=end)

    lines = [f"📅 {label}"]
    lines.append("\n🏫 수업")
    lines += [f"  {c.start:%H:%M}-{c.end:%H:%M} {c.course}" + (f" @{c.location}" if c.location else "")
              for c in classes] or ["  없음"]
    lines.append("\n📝 마감 과제")
    lines += [f"  {a.describe()}" for a in hws] or ["  없음"]
    if exams:
        lines.append("\n🧪 시험")
        lines += [f"  {e.describe()}" for e in exams]
    return "\n".join(lines)


def assignments_text(s: Session, user_id: int, now: datetime) -> str:
    rows = repo.list_assignments(s, user_id, now)
    if not rows:
        return "남은 과제가 없어요 🎉"
    out = ["📝 남은 과제"]
    for a in rows:
        left = a.due_at - now
        d_day = f"D-{left.days}" if left.days > 0 else f"{int(left.total_seconds() // 3600)}시간 남음"
        out.append(f"  {a.describe()} · {d_day}")
    return "\n".join(out)


def exams_text(s: Session, user_id: int, now: datetime) -> str:
    rows = repo.list_exams(s, user_id, now)
    if not rows:
        return "예정된 시험이 없어요."
    return "\n".join(["🧪 예정된 시험"] + [
        f"  {e.describe()} · D-{(e.starts_at.date() - now.date()).days}" for e in rows])


def timetable_text(s: Session, user_id: int) -> str:
    rows = repo.list_classes(s, user_id)
    if not rows:
        return "시간표가 비어 있어요. `/class_add` 로 추가하세요."
    return "\n".join(["🗓 시간표"] + [f"  #{c.id} {c.describe()}" for c in rows])


def week_text(s: Session, user_id: int, now: datetime) -> str:
    until = now + timedelta(days=7)
    hws = repo.list_assignments(s, user_id, now, until=until)
    exams = repo.list_exams(s, user_id, now, until=until)
    lines = ["📆 앞으로 7일"]
    lines.append("\n📝 과제")
    lines += [f"  {a.describe()}" for a in hws] or ["  없음"]
    lines.append("\n🧪 시험")
    lines += [f"  {e.describe()}" for e in exams] or ["  없음"]
    return "\n".join(lines)
