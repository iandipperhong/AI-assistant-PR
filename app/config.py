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
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    allowed_chat_ids: frozenset[int] = field(
        default_factory=lambda: frozenset(_int_list(os.getenv("ALLOWED_CHAT_IDS"), []))
    )

    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini").lower()
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
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

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


settings = Settings()
