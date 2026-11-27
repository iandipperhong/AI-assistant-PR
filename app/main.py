"""진입점. FastAPI 서버 안에서 디스코드 봇과 알림 작업을 함께 돌립니다.

실행:  uvicorn app.main:api --host 127.0.0.1 --port 8000
디스코드 봇은 바깥으로 연결(게이트웨이)하므로 서버 포트를 열 필요가 없습니다.
나중에 웹 대시보드가 필요하면 이 FastAPI 앱에 라우트를 추가하면 됩니다.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.db import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    bot = task = None
    if settings.discord_bot_token:
        from app.bot.client import AssistantBot

        bot = AssistantBot()
        task = asyncio.create_task(bot.start(settings.discord_bot_token))
        task.add_done_callback(_log_crash)
    else:
        log.warning("DISCORD_BOT_TOKEN 이 없어 봇을 시작하지 않습니다 (API만 실행)")
    try:
        yield
    finally:
        if bot is not None:
            await bot.close()
            await asyncio.gather(task, return_exceptions=True)


def _log_crash(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception() is not None:
        log.error("Discord bot stopped", exc_info=task.exception())


api = FastAPI(title="UOS 생활 비서", lifespan=lifespan)


@api.get("/health")
def health() -> dict:
    return {"ok": True, "bot": bool(settings.discord_bot_token), "llm": settings.llm_provider}
