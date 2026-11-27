"""명령어 인자 파싱 (날짜/시간/요일). LLM 없이도 동작하는 부분."""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

from app.models import WEEKDAYS

RELATIVE_DAYS = {"오늘": 0, "내일": 1, "모레": 2, "글피": 3}


class ParseError(ValueError):
    pass


def parse_weekday(token: str) -> int:
    token = token.strip().removesuffix("요일")
    if token in WEEKDAYS:
        return WEEKDAYS.index(token)
    raise ParseError(f"요일을 알 수 없어요: {token} (월~일)")


def parse_time(token: str) -> time:
    m = re.fullmatch(r"(\d{1,2}):?(\d{2})", token.strip())
    if not m:
        raise ParseError(f"시간 형식이 아니에요: {token} (예: 09:00)")
    hour, minute = int(m.group(1)), int(m.group(2))
    if hour == 24 and minute == 0:
        return time(23, 59)
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ParseError(f"시간 범위를 벗어났어요: {token}")
    return time(hour, minute)


def parse_time_range(token: str) -> tuple[time, time]:
    parts = re.split(r"\s*[-~]\s*", token.strip())
    if len(parts) != 2:
        raise ParseError(f"시간 범위 형식이 아니에요: {token} (예: 09:00-10:15)")
    start, end = parse_time(parts[0]), parse_time(parts[1])
    if end <= start:
        raise ParseError("끝나는 시간이 시작 시간보다 늦어야 해요")
    return start, end


def parse_date(token: str, today: date) -> date:
    token = token.strip()
    if token in RELATIVE_DAYS:
        return today + timedelta(days=RELATIVE_DAYS[token])
    m = re.fullmatch(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})", token)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.fullmatch(r"(\d{1,2})[-./](\d{1,2})", token)
    if m:
        candidate = date(today.year, int(m.group(1)), int(m.group(2)))
        # 연도를 안 쓰면 '다가오는 날짜'로 해석 (12월에 1/10 입력 → 내년)
        if candidate < today - timedelta(days=30):
            candidate = candidate.replace(year=today.year + 1)
        return candidate
    raise ParseError(f"날짜 형식이 아니에요: {token} (예: 12/03, 2026-12-03, 내일)")


def parse_when(tokens: list[str], now: datetime, default_time: time) -> tuple[datetime, list[str]]:
    """앞쪽 토큰에서 날짜(+선택적 시간)를 읽고, 남은 토큰을 돌려줍니다."""
    if not tokens:
        raise ParseError("날짜가 필요해요")
    day = parse_date(tokens[0], now.date())
    rest = tokens[1:]
    at = default_time
    if rest and re.fullmatch(r"\d{1,2}:\d{2}", rest[0]):
        at = parse_time(rest[0])
        rest = rest[1:]
    return datetime.combine(day, at), rest
