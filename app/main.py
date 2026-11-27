"""진입점. FastAPI 서버 안에서 텔레그램 봇(롱폴링)과 알림 작업을 함께 돌립니다.

실행:  uvicorn app.main:api --host 127.0.0.1 --port 8000
나중에 웹 대시보드나 웹훅이 필요하면 이 FastAPI 앱에 라우트를 추가하면 됩니다.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from telegram.ext import Application

from app.bot.handlers import register
from app.config import settings
from app.db import init_db
from app.reminders import schedule

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # 토큰이 들어간 URL 로그 방지
log = logging.getLogger("app")


def build_bot() -> Application:
    app = Application.builder().token(settings.telegram_bot_token).build()
    register(app)
    schedule(app)
    return app


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    bot = None
    if settings.telegram_bot_token:
        bot = build_bot()
        await bot.initialize()
        await bot.start()
        await bot.updater.start_polling(drop_pending_updates=True)
        log.info("Telegram bot started (LLM=%s)", settings.llm_provider)
    else:
        log.warning("TELEGRAM_BOT_TOKEN 이 없어 봇을 시작하지 않습니다 (API만 실행)")
    try:
        yield
    finally:
        if bot is not None:
            await bot.updater.stop()
            await bot.stop()
            await bot.shutdown()


api = FastAPI(title="UOS 생활 비서", lifespan=lifespan)


@api.get("/health")
def health() -> dict:
    return {"ok": True, "bot": bool(settings.telegram_bot_token), "llm": settings.llm_provider}
