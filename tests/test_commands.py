from datetime import datetime, timedelta

import pytest

from app import repository as repo
from app.bot import commands as cmd
from app.db import SessionLocal
from app.parsing import ParseError


def test_add_and_list_flow():
    assert "추가했어요" in cmd.class_add(7, "월", "09:00-10:15", "자료구조", "21세기관 301")
    assert "자료구조" in cmd.timetable(7)
    assert "등록했어요" in cmd.hw_add(7, "내일", "운영체제", "과제2", None)
    assert "과제2" in cmd.hw_list(7)
    assert "과제2" in cmd.day(7, 1)
    assert "등록했어요" in cmd.exam_add(7, "모레", "10:00", "자료구조", "기말", None)
    assert "기말" in cmd.week(7)
    # 다른 사용자에게는 안 보임
    assert "없어요" in cmd.hw_list(8)


def test_hw_default_time_is_2359():
    cmd.hw_add(7, "내일", None, "과제", None)
    with SessionLocal() as s:
        due = repo.list_assignments(s, 7, datetime.now() - timedelta(days=1))[0].due_at
    assert (due.hour, due.minute) == (23, 59)


def test_done_and_delete_respect_owner():
    cmd.hw_add(7, "내일", None, "과제", None)
    assert "찾지 못했어요" in cmd.done(8, 1)
    assert "수고했어요" in cmd.done(7, 1)
    assert "찾지 못했어요" in cmd.delete(8, "hw", 1)
    assert "삭제했어요" in cmd.delete(7, "hw", 1)


def test_bad_input_raises_parse_error():
    with pytest.raises(ParseError):
        cmd.class_add(7, "월", "10:00-09:00", "자료구조", None)
    with pytest.raises(ParseError):
        cmd.hw_add(7, "어제쯤", None, "과제", None)
