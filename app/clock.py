from datetime import datetime

from app.config import settings


def now() -> datetime:
    """한국 시간 기준 naive datetime (DB 저장 형식과 동일)."""
    return datetime.now(settings.tz).replace(tzinfo=None)
