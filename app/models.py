"""데이터 모델: 시간표, 과제, 시험, 보낸 알림 기록, 졸업요건용 이수 과목, 학교 공지/학사일정 캐시.

시각은 모두 '한국 시간 기준 naive datetime'으로 저장합니다 (SQLite에 타임존이 없어서).
"""
from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]


class ClassSession(Base):
    """시간표 한 칸 (예: 월 09:00-10:15 자료구조)."""

    __tablename__ = "class_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    course: Mapped[str] = mapped_column(String(100))
    weekday: Mapped[int] = mapped_column(Integer)  # 0=월 ... 6=일
    start: Mapped[time] = mapped_column(Time)
    end: Mapped[time] = mapped_column(Time)
    location: Mapped[str | None] = mapped_column(String(100), nullable=True)

    def describe(self) -> str:
        loc = f" @{self.location}" if self.location else ""
        return f"{WEEKDAYS[self.weekday]} {self.start:%H:%M}-{self.end:%H:%M} {self.course}{loc}"


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    course: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    due_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    # 나중에 LMS(uClass) 자동 가져오기를 붙일 때 중복 방지용
    source: Mapped[str] = mapped_column(String(20), default="manual")
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    def describe(self) -> str:
        course = f"[{self.course}] " if self.course else ""
        mark = "✅ " if self.done else ""
        return f"#{self.id} {mark}{course}{self.title} (마감 {self.due_at:%m/%d %H:%M})"


class Exam(Base):
    __tablename__ = "exams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    course: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(200), default="시험")
    starts_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)  # 시험 범위 (3단계 대비)

    def describe(self) -> str:
        loc = f" @{self.location}" if self.location else ""
        return f"#{self.id} [{self.course}] {self.title} {self.starts_at:%m/%d %H:%M}{loc}"


class SentReminder(Base):
    """같은 알림을 두 번 보내지 않기 위한 기록."""

    __tablename__ = "sent_reminders"
    __table_args__ = (UniqueConstraint("kind", "item_id", "hours_before"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # "assignment" | "exam" | "calendar"
    item_id: Mapped[int] = mapped_column(Integer)
    hours_before: Mapped[int] = mapped_column(Integer)
    sent_at: Mapped[datetime] = mapped_column(DateTime)


class CompletedCourse(Base):
    """졸업요건 계산용: 내가 이미 들은 과목."""

    __tablename__ = "completed_courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    name: Mapped[str] = mapped_column(String(100))
    credits: Mapped[int] = mapped_column(Integer, default=3)
    category: Mapped[str] = mapped_column(String(20), default="전공선택")  # 전공필수/전공선택/교양필수/...


class AcademicEventRow(Base):
    """학교 홈페이지에서 가져온 학사일정 (하루 한 번 새로고침)."""

    __tablename__ = "academic_events"
    __table_args__ = (UniqueConstraint("start", "end", "title"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    start: Mapped[date] = mapped_column(Date, index=True)
    end: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(300))


class SeenNotice(Base):
    """알림 채널에 이미 올린(또는 처음 실행 때 있던) 학과 공지 글 번호."""

    __tablename__ = "seen_notices"

    uid: Mapped[int] = mapped_column(Integer, primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime)


class KeyValue(Base):
    """작은 설정값 저장 (예: 고정된 대시보드 메시지 ID)."""

    __tablename__ = "key_values"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(String(200))


class ChatMessage(Base):
    """대화 기억: 사용자별 최근 대화 (오래된 건 자동 삭제, 사용자당 CHAT_HISTORY_LIMIT 개)."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    role: Mapped[str] = mapped_column(String(10))  # "user" | "bot"
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class Guideline(Base):
    """사용자가 정한 봇 지침 (예: "반말로 해줘"). 매 대화에 넣습니다."""

    __tablename__ = "guidelines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    text: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime)
