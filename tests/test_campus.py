from datetime import date

from app.campus.uos_calendar import parse_calendar
from app.campus.uos_meal import parse_day_menu

# 2026-11-27 에 실제 페이지에서 확인한 구조를 줄여 만든 샘플
MEAL_HTML = """
<div class="listType02 type2"><table><caption>식단</caption>
<tr><th>조식</th><th>중식</th><th>석식</th></tr>
<tr><td class="al">B코너<br>8:30~9:10<br>장터국밥<br><br>*식재료 조달 등 내부 사정으로 메뉴는 변동될 수 있습니다.</td>
<td class="al">B코너<br>(5,000원)<br>간장제육덮밥</td>
<td class="al">C코너<br>돈육콩비지찌개</td></tr></table></div>
"""

CAL_HTML = """
<table><tbody>
<tr style="display:none;"><th>&nbsp;</th><td>&nbsp;</td><td>&nbsp;</td></tr>
<tr><th class="th date01" rowspan="2">2026년<br>01월</th>
<td class="th date02">[12-22 ~ 01-19]</td><td class="al title01"><span>겨울 계절수업</span></td></tr>
<tr><td class="th date02">[01-12 ~ 01-16]</td><td class="al title01"><span>조기졸업 신청</span></td></tr>
<tr><th class="th date01">2026년<br>03월</th>
<td class="th date02">[03-03 ~ 03-03]</td><td class="al title01"><span>2026. 제1학기 개강</span></td></tr>
</tbody></table>
"""


def test_parse_meal():
    menu = parse_day_menu(MEAL_HTML, "020", date(2026, 11, 27))
    assert menu.restaurant == "학생회관 1층"
    assert "장터국밥" in menu.meals["조식"] and "변동" not in menu.meals["조식"]
    assert "간장제육덮밥" in menu.meals["중식"]


def test_parse_calendar_year_crossing():
    events = parse_calendar(CAL_HTML)
    assert events[0].start == date(2025, 12, 22) and events[0].end == date(2026, 1, 19)
    assert events[1].title == "조기졸업 신청"
    assert events[2].start == date(2026, 3, 3)
