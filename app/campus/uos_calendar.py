"""학사일정 파서 (초안, 2단계).

페이지: https://www.uos.ac.kr/korCalendarYear/list.do?list_id=CA1
- 연도는 POST 폼 값 year_code=YYYY (list_id=CA1 함께). 대학원은 별도 사이트.
- 행 구조: th.date01 = "2026년 01월", td.date02 = "[12-22 ~ 01-19]", td.title01 = 일정 이름
- iCal/JSON 같은 공식 API는 찾지 못했습니다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import httpx
from bs4 import BeautifulSoup

BASE = "https://www.uos.ac.kr"


@dataclass
class AcademicEvent:
    start: date
    end: date
    title: str


def parse_calendar(html: str) -> list[AcademicEvent]:
    soup = BeautifulSoup(html, "html.parser")
    events: list[AcademicEvent] = []
    year = month = None
    for tr in soup.select("table tbody tr"):
        th = tr.select_one("th.date01")
        if th is not None:
            m = re.search(r"(\d{4})\D+(\d{1,2})", th.get_text(" "))
            if m:
                year, month = int(m.group(1)), int(m.group(2))
        span = tr.select_one("td.date02")
        title_td = tr.select_one("td.title01")
        if year is None or span is None or title_td is None:
            continue
        m = re.search(r"(\d{1,2})-(\d{1,2})\s*~\s*(\d{1,2})-(\d{1,2})", span.get_text(" "))
        if not m:
            continue
        sm, sd, em, ed = map(int, m.groups())
        # 1월 칸에 "[12-22 ~ 01-19]" 처럼 전년도에서 시작하는 일정이 있음
        start_year = year - 1 if sm > month else year
        end_year = start_year + 1 if em < sm else start_year
        events.append(AcademicEvent(date(start_year, sm, sd), date(end_year, em, ed),
                                    " ".join(title_td.get_text(" ").split())))
    return events


async def fetch_calendar(year: int) -> list[AcademicEvent]:
    async with httpx.AsyncClient(base_url=BASE, follow_redirects=True, timeout=15) as client:
        await client.get("/korCalendarYear/list.do?list_id=CA1")
        r = await client.post("/korCalendarYear/list.do",
                              data={"list_id": "CA1", "year_code": str(year)})
        r.raise_for_status()
    return parse_calendar(r.text)
