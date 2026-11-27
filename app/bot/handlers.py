"""텔레그램 명령어 핸들러."""
from __future__ import annotations

import logging
from datetime import time, timedelta

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app import repository as repo
from app.assistant import handle_message
from app.bot import formatting as fmt
from app.clock import now
from app.config import settings
from app.db import session_scope
from app.llm import LLMError, get_llm
from app.parsing import ParseError, parse_time_range, parse_weekday, parse_when

log = logging.getLogger(__name__)

HELP = """서울시립대 생활 비서 🤖

[등록]
/class_add 월 09:00-10:15 자료구조 @21세기관301
/hw_add 12/03 23:59 자료구조 과제3 보고서
   (시간 생략 시 23:59, 첫 단어는 과목명)
/exam_add 12/10 10:00 자료구조 기말고사 @정보기술관
   (날짜는 12/03, 2026-12-03, 오늘/내일/모레 모두 가능)

[조회]
/today · /tomorrow · /week
/hw · /exams · /timetable

[관리]
/done 3  → 과제 #3 완료
/del hw 3 · /del exam 2 · /del class 1

그냥 말로 물어봐도 돼요: "내일 과제 뭐 있어?", "금요일까지 운영체제 과제2 등록해줘"
"""


def _authorized(update: Update) -> bool:
    if not settings.allowed_chat_ids:
        return True
    return update.effective_chat is not None and update.effective_chat.id in settings.allowed_chat_ids


async def _deny(update: Update) -> None:
    await update.effective_message.reply_text(
        f"허용되지 않은 채팅이에요. 서버의 ALLOWED_CHAT_IDS 에 {update.effective_chat.id} 를 추가하세요.")


def guarded(fn):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _authorized(update):
            return await _deny(update)
        try:
            return await fn(update, context)
        except ParseError as exc:
            await update.effective_message.reply_text(f"⚠️ {exc}\n/help 에서 형식을 확인하세요.")
    wrapper.__name__ = fn.__name__
    return wrapper


def _split_location(tokens: list[str]) -> tuple[list[str], str | None]:
    """'@장소' 토큰을 분리. '@' 뒤 전부를 장소로 봅니다."""
    for i, t in enumerate(tokens):
        if t.startswith("@"):
            loc = " ".join([t[1:]] + tokens[i + 1:]).strip()
            return tokens[:i], loc or None
    return tokens, None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await update.effective_message.reply_text(
        f"안녕하세요! 서울시립대 생활 비서예요.\n이 채팅의 ID: {chat_id}\n\n" + HELP)


@guarded
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(HELP)


@guarded
async def class_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tokens, location = _split_location(context.args)
    if len(tokens) < 3:
        raise ParseError("형식: /class_add 월 09:00-10:15 과목명 @장소")
    weekday = parse_weekday(tokens[0])
    start_t, end_t = parse_time_range(tokens[1])
    course = " ".join(tokens[2:])
    with session_scope() as s:
        row = repo.add_class(s, update.effective_chat.id, course, weekday, start_t, end_t, location)
        msg = f"시간표에 추가했어요: #{row.id} {row.describe()}"
    await update.effective_message.reply_text(msg)


@guarded
async def hw_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    due, rest = parse_when(context.args, now(), default_time=time(23, 59))
    if not rest:
        raise ParseError("형식: /hw_add 12/03 23:59 과목명 과제제목")
    course, title = (rest[0], " ".join(rest[1:])) if len(rest) > 1 else (None, rest[0])
    with session_scope() as s:
        row = repo.add_assignment(s, update.effective_chat.id, title=title, due_at=due, course=course)
        msg = f"과제를 등록했어요: {row.describe()}"
    await update.effective_message.reply_text(msg)


@guarded
async def exam_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tokens, location = _split_location(context.args)
    starts, rest = parse_when(tokens, now(), default_time=time(9, 0))
    if not rest:
        raise ParseError("형식: /exam_add 12/10 10:00 과목명 시험이름 @장소")
    course = rest[0]
    title = " ".join(rest[1:]) or "시험"
    with session_scope() as s:
        row = repo.add_exam(s, update.effective_chat.id, course, starts, title, location)
        msg = f"시험을 등록했어요: {row.describe()}"
    await update.effective_message.reply_text(msg)


@guarded
async def today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    n = now()
    with session_scope() as s:
        text = fmt.day_summary(s, update.effective_chat.id, n.date(), n)
    await update.effective_message.reply_text(text)


@guarded
async def tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    n = now()
    with session_scope() as s:
        text = fmt.day_summary(s, update.effective_chat.id, n.date() + timedelta(days=1), n)
    await update.effective_message.reply_text(text)


@guarded
async def week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with session_scope() as s:
        text = fmt.week_text(s, update.effective_chat.id, now())
    await update.effective_message.reply_text(text)


@guarded
async def hw_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with session_scope() as s:
        text = fmt.assignments_text(s, update.effective_chat.id, now())
    await update.effective_message.reply_text(text)


@guarded
async def exams(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with session_scope() as s:
        text = fmt.exams_text(s, update.effective_chat.id, now())
    await update.effective_message.reply_text(text)


@guarded
async def timetable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with session_scope() as s:
        text = fmt.timetable_text(s, update.effective_chat.id)
    await update.effective_message.reply_text(text)


@guarded
async def done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 1 or not context.args[0].lstrip("#").isdigit():
        raise ParseError("형식: /done 과제번호")
    with session_scope() as s:
        row = repo.mark_assignment_done(s, update.effective_chat.id, int(context.args[0].lstrip("#")))
        msg = f"수고했어요! {row.describe()}" if row else "그 번호의 과제를 찾지 못했어요."
    await update.effective_message.reply_text(msg)


@guarded
async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 2 or context.args[0] not in repo.MODELS or not context.args[1].lstrip("#").isdigit():
        raise ParseError("형식: /del hw 3  (종류: class, hw, exam)")
    with session_scope() as s:
        ok = repo.delete_item(s, update.effective_chat.id, context.args[0], int(context.args[1].lstrip("#")))
    await update.effective_message.reply_text("삭제했어요." if ok else "그 항목을 찾지 못했어요.")


@guarded
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        llm = get_llm()
    except LLMError as exc:
        await update.effective_message.reply_text(f"AI 설정이 아직 안 됐어요 ({exc}). 명령어는 /help 참고.")
        return
    with session_scope() as s:
        reply = await handle_message(llm, s, update.effective_chat.id, update.effective_message.text, now())
    await update.effective_message.reply_text(reply)


def register(app: Application) -> None:
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("class_add", class_add))
    app.add_handler(CommandHandler("hw_add", hw_add))
    app.add_handler(CommandHandler("exam_add", exam_add))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("tomorrow", tomorrow))
    app.add_handler(CommandHandler("week", week))
    app.add_handler(CommandHandler("hw", hw_list))
    app.add_handler(CommandHandler("exams", exams))
    app.add_handler(CommandHandler("timetable", timetable))
    app.add_handler(CommandHandler("done", done))
    app.add_handler(CommandHandler("del", delete))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
