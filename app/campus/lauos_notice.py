"""조경학과 홈페이지 공지 게시판.

페이지: https://lauos.or.kr/notice  (워드프레스 KBoard 게시판)
- 목록: table tbody tr. 글 번호는 링크의 uid= 값, 제목은 .kboard-default-cut-strings, 날짜는 td.kboard-list-date
- 상단 고정 공지(tr.kboard-list-notice)도 같은 구조라 uid 로 중복을 없앱니다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

BASE = "https://lauos.or.kr"
LIST_URL = f"{BASE}/notice"


@dataclass(frozen=True)
class Notice:
    uid: int
    title: str
    date: str  # "2026.11.19"

    @property
    def url(self) -> str:
        return f"{LIST_URL}?uid={self.uid}&mod=document"


def parse_notices(html: str) -> list[Notice]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[Notice] = []
    seen: set[int] = set()
    for tr in soup.select("table tbody tr"):
        a = tr.select_one("td.kboard-list-title a[href]")
        if a is None:
            continue
        m = re.search(r"uid=(\d+)", a["href"])
        if not m or int(m.group(1)) in seen:
            continue
        uid = int(m.group(1))
        seen.add(uid)
        box = a.select_one(".kboard-default-cut-strings") or a
        for extra in box.select(".kboard-comments-count"):
            extra.decompose()
        title = " ".join(box.get_text(" ").split())
        date_td = tr.select_one("td.kboard-list-date")
        out.append(Notice(uid, title, date_td.get_text(strip=True) if date_td else ""))
    return out


def format_notices(notices: list[Notice], limit: int = 10) -> str:
    if not notices:
        return "공지를 불러오지 못했어요."
    lines = ["📢 **조경학과 공지** (lauos.or.kr)"]
    for n in notices[:limit]:
        lines.append(f"• {n.date} [{n.title}](<{n.url}>)")
    return "\n".join(lines)


async def fetch_notices() -> list[Notice]:
    async with httpx.AsyncClient(follow_redirects=True, timeout=15,
                                 headers={"User-Agent": "Mozilla/5.0 (uos-assistant bot)"}) as client:
        r = await client.get(LIST_URL)
        r.raise_for_status()
    return parse_notices(r.text)
