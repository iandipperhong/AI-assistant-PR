"""데이터 모델: 시간표, 과제, 시험, 보낸 알림 기록.

시각은 모두 '한국 시간 기준 naive datetime'으로 저장합니다 (SQLite에 타임존이 없어서).
"""
from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, Time, UniqueConstraint
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
    kind: Mapped[str] = mapped_column(String(20))  # "assignment" | "exam"
    item_id: Mapped[int] = mapped_column(Integer)
    hours_before: Mapped[int] = mapped_column(Integer)
    sent_at: Mapped[datetime] = mapped_column(DateTime)
