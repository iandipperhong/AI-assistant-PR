"""마감 알림. python-telegram-bot 의 JobQueue 가 주기적으로 check_reminders 를 부릅니다."""
from __future__ import annotations

import logging
from datetime import datetime

from telegram.ext import Application, ContextTypes

from app import repository as repo
from app.clock import now
from app.config import settings
from app.db import session_scope

log = logging.getLogger(__name__)


def _label(hours: int) -> str:
    return f"{hours // 24}일" if hours % 24 == 0 and hours >= 24 else f"{hours}시간"


def collect_messages(at: datetime) -> list[tuple[int, str]]:
    """보낼 (chat_id, 메시지) 목록을 만들고 '보냄'으로 기록합니다."""
    out: list[tuple[int, str]] = []
    with session_scope() as s:
        for kind, item, hours in repo.due_reminders(
                s, at, settings.assignment_remind_hours, settings.exam_remind_hours):
            if kind == "assignment":
                text = f"⏰ 과제 마감 {_label(hours)} 이내!\n{item.describe()}\n끝냈으면 /done {item.id}"
                all_hours = settings.assignment_remind_hours
            else:
                text = f"🧪 시험 {_label(hours)} 이내!\n{item.describe()}"
                all_hours = settings.exam_remind_hours
            out.append((item.chat_id, text))
            repo.record_reminder(s, kind, item.id, hours, at)
            repo.mark_older_windows_sent(s, kind, item.id, hours, all_hours, at)
    return out


async def check_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    for chat_id, text in collect_messages(now()):
        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
        except Exception:  # 한 건 실패가 나머지 알림을 막지 않게
            log.exception("reminder send failed (chat %s)", chat_id)


def schedule(app: Application) -> None:
    app.job_queue.run_repeating(check_reminders, interval=settings.reminder_interval_seconds, first=10)
