"""학식 식단표.

페이지: https://www.uos.ac.kr/food/placeList.do
- 식당 코드 rstcde: 020=학생회관 1층(기본), 010=100주년기념관 이룸라운지, 030=양식당, 040=자연과학관
- 날짜는 POST 폼 값 search_date=YYYYMMDD 로 바꿉니다 (GET 쿼리로는 안 먹힘).
- 그냥 접속하면 SSO 페이지가 자바스크립트로 돌려보내는데, 주소에 identified=anonymous 를 붙이면
  쿠키 없이 바로 열립니다 (2026-11-27 확인).
- 서버 렌더링 HTML. 'div.listType02' 안 첫 번째 table 의 td 3개가 조식/중식/석식.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date

import httpx
from bs4 import BeautifulSoup

BASE = "https://www.uos.ac.kr"
# 드롭다운에 보일 순서
RESTAURANTS = {
    "020": "학생회관 1층",
    "010": "100주년기념관 이룸라운지",
    "030": "양식당",
    "040": "자연과학관",
}
MEALS = ("조식", "중식", "석식")
NOTICE = "*식재료 조달 등 내부 사정으로"
_CACHE_SECONDS = 600
_cache: dict[tuple[str, date], tuple[float, "DayMenu"]] = {}


@dataclass
class DayMenu:
    restaurant: str
    day: date
    meals: dict[str, str]  # {"조식": "...", "중식": "...", "석식": "..."}


def parse_day_menu(html: str, restaurant_code: str, day: date) -> DayMenu:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("div.listType02 table")
    meals: dict[str, str] = {}
    if table is not None:
        cells = table.select("td")
        for name, td in zip(MEALS, cells):
            lines = [ln.strip() for ln in td.get_text("\n").splitlines()]
            lines = [ln for ln in lines if ln and not ln.startswith(NOTICE)]
            meals[name] = "\n".join(lines)
    return DayMenu(RESTAURANTS.get(restaurant_code, restaurant_code), day, meals)


def format_menu(menu: DayMenu) -> str:
    out = [f"🍚 **{menu.restaurant}** · {menu.day:%m/%d}"]
    any_meal = False
    for name in MEALS:
        text = menu.meals.get(name, "").strip()
        if text:
            any_meal = True
            out.append(f"\n**{name}**\n{text}")
    if not any_meal:
        out.append("\n오늘은 식단이 없어요 (주말·방학이거나 아직 안 올라왔어요).")
    return "\n".join(out)


async def fetch_day_menu(day: date, restaurant_code: str = "020") -> DayMenu:
    key = (restaurant_code, day)
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < _CACHE_SECONDS:
        return hit[1]
    async with httpx.AsyncClient(base_url=BASE, follow_redirects=True, timeout=15,
                                 headers={"User-Agent": "Mozilla/5.0 (uos-assistant bot)"}) as client:
        r = await client.post("/food/placeList.do",
                              params={"identified": "anonymous", "rstcde": restaurant_code},
                              data={"search_date": day.strftime("%Y%m%d")})
        r.raise_for_status()
    menu = parse_day_menu(r.text, restaurant_code, day)
    _cache.clear()  # 메모리 절약: 마지막 몇 개만 들고 있으면 충분
    _cache[key] = (time.monotonic(), menu)
    return menu
