from datetime import date, datetime

from app import repository as repo
from app.bot import commands as cmd
from app.campus.lauos_notice import Notice, parse_notices
from app.campus.uos_calendar import AcademicEvent, clean_title, parse_calendar
from app.campus.uos_meal import format_menu, parse_day_menu
from app.campus_alerts import calendar_alert_messages, calendar_text, new_notice_messages
from app.db import session_scope

# 2026-11-27 lauos.or.kr/notice 에서 확인한 구조를 줄인 샘플
NOTICE_HTML = """
<div class="kboard-list"><table><thead><tr><td class="kboard-list-uid">번호</td></tr></thead><tbody>
<tr class="kboard-list-notice"><td class="kboard-list-uid">공지</td><td class="kboard-list-title">
<a href="/notice?uid=1999&amp;mod=document&amp;pageid=1"><div class="kboard-default-cut-strings">
학과 사무실 운영시간 <span class="kboard-comments-count">(2)</span></div></a></td>
<td class="kboard-list-date">2026.03.02</td></tr>
<tr class=""><td class="kboard-list-uid">306</td><td class="kboard-list-title">
<a href="/notice?uid=2073&amp;mod=document&amp;pageid=1"><div class="kboard-default-cut-strings">
[특강] 미래도시의 비전과 구상 <span class="kboard-comments-count"></span></div></a>
<div class="kboard-mobile-contents"><span class="contents-item kboard-date">2026.11.19</span></div></td>
<td class="kboard-list-user">조경학과</td><td class="kboard-list-date">2026.11.19</td></tr>
<tr class=""><td class="kboard-list-uid">305</td><td class="kboard-list-title">
<a href="/notice?uid=2072&amp;mod=document&amp;pageid=1"><div class="kboard-default-cut-strings">
2026학년도 2학기 조경학과 상담주간</div></a></td><td class="kboard-list-date">2026.11.18</td></tr>
</tbody></table></div>
"""

CAL_HTML = """<table><tbody>
<tr><th class="th date01">2026년<br>11월</th>
<td class="th date02">[11-16 ~ 11-20]</td><td class="al title01"><span>2027. 1학기 전과, 재입학 신청 [2027 1st semester department transfer]</span></td></tr>
<tr><th class="th date01">2026년<br>12월</th>
<td class="th date02">[12-07 ~ 12-11]</td><td class="al title01"><span>2027. 1학기 학부 교내장학 신청(1차) [2027 scholarship (1st round)]</span></td></tr>
<tr><td class="th date02">[12-22 ~ 01-19]</td><td class="al title01"><span>겨울 계절수업 [Winter session]</span></td></tr>
<tr><th class="th date01">2027년<br>01월</th>
<td class="th date02">[12-22 ~ 01-19]</td><td class="al title01"><span>겨울 계절수업 [Winter session]</span></td></tr>
</tbody></table>"""


def test_parse_notices():
    notices = parse_notices(NOTICE_HTML)
    assert [n.uid for n in notices] == [1999, 2073, 2072]
    assert notices[1].title == "[특강] 미래도시의 비전과 구상"
    assert notices[0].title == "학과 사무실 운영시간"
    assert notices[1].date == "2026.11.19"
    assert notices[1].url.endswith("uid=2073&mod=document")


def test_new_notice_first_run_is_silent_then_posts_new():
    at = datetime(2026, 11, 27, 12)
    old = parse_notices(NOTICE_HTML)
    assert new_notice_messages(old, at) == []  # 처음엔 도배하지 않음
    assert new_notice_messages(old, at) == []
    fresh = [Notice(2080, "2027 수강신청 안내", "2026.11.28")] + old
    msgs = new_notice_messages(fresh, at)
    assert len(msgs) == 1 and "2027 수강신청 안내" in msgs[0] and "uid=2080" in msgs[0]
    assert new_notice_messages(fresh, at) == []


def test_calendar_dedup_and_clean_title():
    events = parse_calendar(CAL_HTML)
    assert len(events) == 3  # 겨울 계절수업 중복 제거
    assert events[0].title == "2027. 1학기 전과, 재입학 신청"
    assert events[2] == AcademicEvent(date(2026, 12, 22), date(2027, 1, 19), "겨울 계절수업")
    assert clean_title("성적정정 [Grade correction]") == "성적정정"
    assert clean_title("기말시험") == "기말시험"


def _store_events():
    with session_scope() as s:
        repo.replace_academic_events(s, parse_calendar(CAL_HTML), {2026})


def test_calendar_alerts_7_days_and_day_before():
    _store_events()
    # 장학 신청 12/07 시작 → 11/30 에 7일 전 알림
    assert calendar_alert_messages(datetime(2026, 11, 30, 8)) == []  # 9시 전엔 안 보냄
    msgs = calendar_alert_messages(datetime(2026, 11, 30, 10))
    assert len(msgs) == 1 and "7일 뒤" in msgs[0] and "장학" in msgs[0]
    assert calendar_alert_messages(datetime(2026, 11, 30, 11)) == []  # 한 번만
    msgs = calendar_alert_messages(datetime(2026, 12, 6, 9))
    assert len(msgs) == 1 and "내일" in msgs[0]
    # 계절수업은 '중요' 키워드가 아니라 알림 없음
    assert calendar_alert_messages(datetime(2026, 12, 21, 9)) == []


def test_calendar_refresh_keeps_ids():
    _store_events()
    with session_scope() as s:
        ids = [r.id for r in repo.list_academic_events(s, date(2026, 1, 1))]
    _store_events()
    with session_scope() as s:
        assert [r.id for r in repo.list_academic_events(s, date(2026, 1, 1))] == ids


def test_calendar_text():
    _store_events()
    text = calendar_text(date(2026, 11, 27))
    assert "장학" in text and "⭐" in text and "전과" not in text  # 전과 신청은 이미 끝남


def test_format_menu_empty_and_full():
    menu = parse_day_menu("<div class='listType02'><table><tr><td>A코너<br>김밥</td><td></td><td></td>"
                          "</tr></table></div>", "010", date(2026, 11, 27))
    text = format_menu(menu)
    assert "100주년기념관" in text and "김밥" in text and "중식" not in text
    assert "식단이 없어요" in format_menu(parse_day_menu("<html></html>", "040", date(2026, 11, 28)))


def test_graduation_flow():
    text = cmd.grad_summary(7)
    assert "요람 확인 필요" in text and "조경학개론" in text
    assert "2과목 추가" in cmd.grad_quick_add(7, ["조경학개론", "기초설계"])
    assert "이미 다" in cmd.grad_quick_add(7, ["조경학 개론"])  # 띄어쓰기 달라도 중복
    assert "교양필수, 2학점" in cmd.grad_add(7, "대학영어", "2", "교필")
    text = cmd.grad_summary(7)
    assert "총: 8학점" in text and "조경학개론" not in text.split("1학년:")[1].split("\n")[0]
    assert "기초컴퓨터설계" in text
    # 다른 사람 과목은 못 지움
    assert "찾지 못했어요" in cmd.grad_delete(8, [1])
    assert "1과목 삭제" in cmd.grad_delete(7, [1])


def test_graduation_rules_when_filled():
    from app import graduation
    from app.models import CompletedCourse

    courses = [CompletedCourse(name="조경학개론", credits=3, category="전공필수"),
               CompletedCourse(name="대학영어", credits=2, category="교양필수")]
    text = graduation.summary(courses, rules={"총": 130, "전공필수": 6}, required=["조경학개론", "조경계획"],
                              prereq={"조경캡스톤디자인": ["조경계획"]})
    assert "총: 5 / 130학점 · 125학점 남음" in text
    assert "전공필수: 3 / 6학점 · 3학점 남음" in text
    assert "전공필수 미이수**\n  조경계획" in text
    assert "조경캡스톤디자인 ← 먼저: 조경계획" in text


def test_grad_add_validation():
    import pytest

    from app.parsing import ParseError
    with pytest.raises(ParseError):
        cmd.grad_add(7, "과목", "열", None)
    with pytest.raises(ParseError):
        cmd.grad_add(7, "과목", "3", "아무거나")
    assert "전공선택" in cmd.grad_add(7, "조경계획", "", "")


def test_curriculum_aliases_and_semesters():
    from app.campus import landscape_curriculum as cur

    assert set(cur.SEMESTERS) <= {cur.normalize(c) for c in cur.ALL_MAJOR_COURSES}
    assert cur.normalize("공원 및 오픈스페이스설계 스튜디오") == cur.normalize("공원및그린네트워크설계스튜디오")
    assert cur.semester_label("조경 캡스톤디자인") == "4학년 1학기"
    assert cur.semester_label("환경심리학") is None
    cmd.grad_quick_add(7, ["단지및커뮤니티공간설계스튜디오"])
    assert "이미 다" in cmd.grad_quick_add(7, ["단지 및 기반시설설계 스튜디오"])
