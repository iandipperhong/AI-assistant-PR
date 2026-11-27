from datetime import datetime, timedelta

from app import repository as repo
from app.reminders import collect_messages

NOW = datetime(2026, 11, 27, 12, 0)


def test_assignment_reminders_fire_once_per_window(session):
    repo.add_assignment(session, 1, "과제3", NOW + timedelta(hours=20), course="자료구조")
    session.commit()

    first = collect_messages(NOW)
    assert len(first) == 1 and "1일" in first[0][1]
    assert collect_messages(NOW + timedelta(minutes=5)) == []  # 중복 없음

    later = collect_messages(NOW + timedelta(hours=18))  # 마감 2시간 전
    assert len(later) == 1 and "3시간" in later[0][1]


def test_late_registration_skips_older_window(session):
    # 마감 2시간 전에 등록 → 3시간 알림 하나만, 24시간 알림은 안 옴
    repo.add_assignment(session, 1, "급한 과제", NOW + timedelta(hours=2))
    session.commit()
    assert len(collect_messages(NOW)) == 1
    assert collect_messages(NOW + timedelta(minutes=30)) == []


def test_done_assignment_not_reminded(session):
    a = repo.add_assignment(session, 1, "끝낸 과제", NOW + timedelta(hours=2))
    repo.mark_assignment_done(session, 1, a.id)
    session.commit()
    assert collect_messages(NOW) == []


def test_exam_reminder(session):
    repo.add_exam(session, 1, "운영체제", NOW + timedelta(days=2), title="기말")
    session.commit()
    msgs = collect_messages(NOW)
    assert len(msgs) == 1 and "3일" in msgs[0][1]
