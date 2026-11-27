"""학사일정.

페이지: https://www.uos.ac.kr/korCalendarYear/list.do?list_id=CA1
- 연도는 POST 폼 값 year_code=YYYY (list_id=CA1 함께). 주소에 identified=anonymous 를 붙이면 SSO 를 건너뜀.
- 행 구조: th.date01 = "2026년 01월", td.date02 = "[12-22 ~ 01-19]", td.title01 = 일정 이름 (한/영 병기)
- 여러 달에 걸친 일정은 달마다 한 번씩 또 나오므로 중복을 없앱니다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import httpx
from bs4 import BeautifulSoup

BASE = "https://www.uos.ac.kr"

# 알림 채널로 미리 알려 줄 일정 (제목에 이 단어가 있으면)
IMPORTANT_KEYWORDS = ("수강", "장학", "휴학", "복학", "조기졸업", "전과", "복수전공", "부전공",
                      "재입학", "기말시험", "중간시험", "등록금", "졸업")


@dataclass(frozen=True)
class AcademicEvent:
    start: date
    end: date
    title: str

    def describe(self) -> str:
        if self.start == self.end:
            return f"{self.start:%m/%d} {self.title}"
        return f"{self.start:%m/%d}~{self.end:%m/%d} {self.title}"


def clean_title(raw: str) -> str:
    text = " ".join(raw.split())
    # 뒤에 붙은 영어 번역 "[Winter session]" 제거
    return re.sub(r"\s*\[[^\]]*[A-Za-z][^\]]*\]\s*$", "", text).strip()


def is_important(title: str) -> bool:
    return any(k in title for k in IMPORTANT_KEYWORDS)


def parse_calendar(html: str) -> list[AcademicEvent]:
    soup = BeautifulSoup(html, "html.parser")
    events: list[AcademicEvent] = []
    seen: set[AcademicEvent] = set()
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
        ev = AcademicEvent(date(start_year, sm, sd), date(end_year, em, ed), clean_title(title_td.get_text(" ")))
        if ev not in seen:
            seen.add(ev)
            events.append(ev)
    return events


async def fetch_calendar(year: int) -> list[AcademicEvent]:
    async with httpx.AsyncClient(base_url=BASE, follow_redirects=True, timeout=20,
                                 headers={"User-Agent": "Mozilla/5.0 (uos-assistant bot)"}) as client:
        r = await client.post("/korCalendarYear/list.do", params={"identified": "anonymous"},
                              data={"list_id": "CA1", "year_code": str(year)})
        r.raise_for_status()
    return parse_calendar(r.text)
