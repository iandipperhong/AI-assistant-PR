from datetime import date, datetime, time

import pytest

from app.parsing import ParseError, parse_date, parse_time_range, parse_weekday, parse_when

TODAY = date(2026, 11, 27)  # 금요일


def test_weekday():
    assert parse_weekday("월") == 0
    assert parse_weekday("금요일") == 4
    with pytest.raises(ParseError):
        parse_weekday("X")


def test_time_range():
    assert parse_time_range("09:00-10:15") == (time(9, 0), time(10, 15))
    assert parse_time_range("9:00~10:15") == (time(9, 0), time(10, 15))
    with pytest.raises(ParseError):
        parse_time_range("10:00-09:00")


@pytest.mark.parametrize("token,expected", [
    ("오늘", date(2026, 11, 27)),
    ("내일", date(2026, 11, 28)),
    ("12/03", date(2026, 12, 3)),
    ("2026-12-03", date(2026, 12, 3)),
    ("1/10", date(2027, 1, 10)),  # 지난 날짜면 내년으로
])
def test_date(token, expected):
    assert parse_date(token, TODAY) == expected


def test_when_default_and_explicit_time():
    now = datetime(2026, 11, 27, 12, 0)
    dt, rest = parse_when(["12/03", "자료구조", "과제3"], now, time(23, 59))
    assert dt == datetime(2026, 12, 3, 23, 59) and rest == ["자료구조", "과제3"]
    dt, rest = parse_when(["내일", "10:00", "OS"], now, time(23, 59))
    assert dt == datetime(2026, 11, 28, 10, 0) and rest == ["OS"]
