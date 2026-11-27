"""마감 알림 계산. 디스코드 봇의 반복 작업(app/bot/client.py)이 주기적으로 collect_messages 를 부릅니다."""
from __future__ import annotations

from datetime import datetime

from app import repository as repo
from app.config import settings
from app.db import session_scope


def _label(hours: int) -> str:
    return f"{hours // 24}일" if hours % 24 == 0 and hours >= 24 else f"{hours}시간"


def collect_messages(at: datetime) -> list[tuple[int, str]]:
    """보낼 (user_id, 메시지) 목록을 만들고 '보냄'으로 기록합니다."""
    out: list[tuple[int, str]] = []
    with session_scope() as s:
        for kind, item, hours in repo.due_reminders(
                s, at, settings.assignment_remind_hours, settings.exam_remind_hours):
            if kind == "assignment":
                text = f"⏰ 과제 마감 {_label(hours)} 이내!\n{item.describe()}\n끝냈으면 `/done id:{item.id}`"
                all_hours = settings.assignment_remind_hours
            else:
                text = f"🧪 시험 {_label(hours)} 이내!\n{item.describe()}"
                all_hours = settings.exam_remind_hours
            out.append((item.user_id, text))
            repo.record_reminder(s, kind, item.id, hours, at)
            repo.mark_older_windows_sent(s, kind, item.id, hours, all_hours, at)
    return out
