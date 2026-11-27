"""#알림 채널로 보낼 내용 계산 (학과 새 공지, 학사일정 미리 알림) + 대시보드용 학사일정 글.

디스코드와 분리된 순수 함수라 테스트하기 쉽습니다. 반복 작업은 app/bot/client.py 에 있습니다.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from app import repository as repo
from app.campus import uos_calendar
from app.campus.lauos_notice import Notice
from app.config import settings
from app.db import session_scope
from app.models import WEEKDAYS

log = logging.getLogger(__name__)


def new_notice_messages(notices: list[Notice], at: datetime) -> list[str]:
    """처음 실행이면 지금 있는 글은 '본 것'으로만 기록(옛 글 도배 방지). 그 뒤로는 새 글마다 메시지 하나."""
    with session_scope() as s:
        seen = repo.seen_notice_uids(s)
        first_run = not seen
        fresh = [n for n in notices if n.uid not in seen]
        repo.mark_notices_seen(s, [n.uid for n in notices], at)
    if first_run:
        return []
    return [f"📢 **조경학과 새 공지** ({n.date})\n{n.title}\n<{n.url}>" for n in sorted(fresh, key=lambda n: n.uid)]


async def refresh_calendar(today: date) -> int:
    """학교 홈페이지에서 올해(11·12월이면 내년도) 학사일정을 받아 DB 에 저장."""
    years = {today.year} | ({today.year + 1} if today.month >= 11 else set())
    events = []
    for y in sorted(years):
        events += await uos_calendar.fetch_calendar(y)
    # 내년 페이지에 아직 아무것도 없으면 그 해 일정은 건드리지 않음
    got_years = {e.start.year for e in events}
    with session_scope() as s:
        repo.replace_academic_events(s, events, years & got_years)
    return len(events)


def _d_label(days: int) -> str:
    return "내일" if days == 1 else f"{days}일 뒤"


def calendar_alert_messages(at: datetime) -> list[str]:
    """중요 학사일정(수강신청·장학금·휴복학 등) 시작 7일 전·1일 전 알림. 같은 알림은 한 번만."""
    if at.hour < settings.calendar_alert_hour:
        return []
    today = at.date()
    days_list = sorted(settings.calendar_remind_days, reverse=True)
    out = []
    with session_scope() as s:
        sent = repo.sent_keys(s, "calendar")
        horizon = today + timedelta(days=max(days_list, default=0))
        for ev in repo.list_academic_events(s, today, horizon):
            if not uos_calendar.is_important(ev.title):
                continue
            left = (ev.start - today).days
            if left not in days_list or (ev.id, left * 24) in sent:
                continue
            span = f"{ev.start:%m/%d}({WEEKDAYS[ev.start.weekday()]})"
            if ev.end != ev.start:
                span += f" ~ {ev.end:%m/%d}({WEEKDAYS[ev.end.weekday()]})"
            out.append(f"📅 **학사일정 {_d_label(left)} 시작**\n{ev.title}\n{span}")
            repo.record_reminder(s, "calendar", ev.id, left * 24, at)
            # 7일 전 알림을 놓치고 1일 전에 보냈다면 7일 전 것은 보낸 셈 치기
            for d in days_list:
                if d > left and (ev.id, d * 24) not in sent:
                    repo.record_reminder(s, "calendar", ev.id, d * 24, at)
    return out


def calendar_text(today: date, days: int = 45) -> str:
    with session_scope() as s:
        rows = repo.list_academic_events(s, today, today + timedelta(days=days))
    if not rows:
        return "학사일정을 아직 불러오지 못했어요. 잠시 뒤 다시 눌러 주세요."
    lines = [f"📅 **학사일정** (앞으로 {days}일)"]
    for r in rows:
        mark = "⭐ " if uos_calendar.is_important(r.title) else ""
        span = f"{r.start:%m/%d}" if r.start == r.end else f"{r.start:%m/%d}~{r.end:%m/%d}"
        now_tag = " ← 진행 중" if r.start <= today <= r.end else ""
        lines.append(f"  {span} {mark}{r.title}{now_tag}")
    lines.append("\n⭐ 표시는 #알림 채널에 7일 전·전날 알려 드려요.")
    return "\n".join(lines)


def has_calendar(today: date) -> bool:
    with session_scope() as s:
        return bool(repo.list_academic_events(s, today, today + timedelta(days=365)))
