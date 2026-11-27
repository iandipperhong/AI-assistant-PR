"""학식 식단표 파서 (초안, 2단계).

페이지: https://www.uos.ac.kr/food/placeList.do
- 식당 코드 rstcde: 020=학생회관 1층(기본), 010=100주년기념관 이룸라운지, 030=양식당, 040=자연과학관
- 날짜는 POST 폼 값 search_date=YYYYMMDD 로 바꿉니다 (GET 쿼리로는 안 먹힘).
- 서버 렌더링 HTML. 'div.listType02' 안 첫 번째 table 의 td 3개가 조식/중식/석식.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import httpx
from bs4 import BeautifulSoup

BASE = "https://www.uos.ac.kr"
RESTAURANTS = {"020": "학생회관 1층", "010": "이룸라운지", "030": "양식당", "040": "자연과학관"}
MEALS = ("조식", "중식", "석식")
NOTICE = "*식재료 조달 등 내부 사정으로"


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


async def fetch_day_menu(day: date, restaurant_code: str = "020") -> DayMenu:
    # 첫 요청 시 SSO 페이지를 거쳐 identified=anonymous 로 돌아옵니다. 쿠키 유지가 필요해서 Client 재사용.
    async with httpx.AsyncClient(base_url=BASE, follow_redirects=True, timeout=15) as client:
        await client.get("/food/placeList.do")
        r = await client.post(f"/food/placeList.do?rstcde={restaurant_code}",
                              data={"search_date": day.strftime("%Y%m%d")})
        r.raise_for_status()
    return parse_day_menu(r.text, restaurant_code, day)
