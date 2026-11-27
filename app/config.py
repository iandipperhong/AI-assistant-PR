"""환경변수 기반 설정."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _int_list(value: str | None, default: list[int]) -> list[int]:
    if not value:
        return default
    return [int(v) for v in value.split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    discord_bot_token: str = os.getenv("DISCORD_BOT_TOKEN", "")
    # 슬래시 명령어를 즉시 반영할 서버 ID (비우면 전역 등록: 반영까지 최대 1시간)
    discord_guild_id: int | None = int(os.getenv("DISCORD_GUILD_ID")) if os.getenv("DISCORD_GUILD_ID") else None
    allowed_user_ids: frozenset[int] = field(
        default_factory=lambda: frozenset(_int_list(os.getenv("ALLOWED_USER_IDS"), []))
    )

    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini").lower()
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-haiku-5-5")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.1")

    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/assistant.db")
    timezone: str = os.getenv("TIMEZONE", "Asia/Seoul")

    assignment_remind_hours: list[int] = field(
        default_factory=lambda: _int_list(os.getenv("ASSIGNMENT_REMIND_HOURS"), [24, 3])
    )
    exam_remind_hours: list[int] = field(
        default_factory=lambda: _int_list(os.getenv("EXAM_REMIND_HOURS"), [72, 24])
    )
    reminder_interval_seconds: int = int(os.getenv("REMINDER_INTERVAL_SECONDS", "300"))

    # 버튼 대시보드를 고정할 채널, 학과 공지·학사일정 알림을 올릴 채널 (디스코드 채널 ID)
    dashboard_channel_id: int | None = int(os.getenv("DASHBOARD_CHANNEL_ID")) if os.getenv("DASHBOARD_CHANNEL_ID") else None
    alert_channel_id: int | None = int(os.getenv("ALERT_CHANNEL_ID")) if os.getenv("ALERT_CHANNEL_ID") else None
    notice_check_minutes: int = int(os.getenv("NOTICE_CHECK_MINUTES", "30"))
    # 학사일정 알림: 시작 며칠 전에 알릴지, 몇 시 이후에 보낼지
    calendar_remind_days: list[int] = field(
        default_factory=lambda: _int_list(os.getenv("CALENDAR_REMIND_DAYS"), [7, 1])
    )
    calendar_alert_hour: int = int(os.getenv("CALENDAR_ALERT_HOUR", "9"))

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


settings = Settings()
