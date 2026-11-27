"""디스코드 봇: 슬래시 명령어 등록, 자연어 메시지 처리, DM 알림 반복 작업."""
from __future__ import annotations

import logging
import re
from collections.abc import Callable

import discord
from discord import app_commands
from discord.ext import tasks

from app.assistant import handle_message
from app.bot import commands as cmd
from app.clock import now
from app.config import settings
from app.db import session_scope
from app.llm import LLMError, get_llm
from app.parsing import ParseError
from app.reminders import collect_messages

log = logging.getLogger(__name__)

WEEKDAY_CHOICES = [app_commands.Choice(name=d, value=d) for d in "월화수목금토일"]
KIND_CHOICES = [
    app_commands.Choice(name="과제", value="hw"),
    app_commands.Choice(name="시험", value="exam"),
    app_commands.Choice(name="수업(시간표)", value="class"),
]


def is_allowed(user_id: int) -> bool:
    return not settings.allowed_user_ids or user_id in settings.allowed_user_ids


class GuardedTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.command and interaction.command.name == "whoami":
            return True
        if is_allowed(interaction.user.id):
            return True
        await interaction.response.send_message(
            f"허용되지 않은 사용자예요. 서버의 ALLOWED_USER_IDS 에 {interaction.user.id} 를 추가하세요.",
            ephemeral=True)
        return False


async def _reply(interaction: discord.Interaction, fn: Callable[[], str]) -> None:
    """명령 실행 → 답장. 서버 채널에서는 나만 보이게(ephemeral) 보냅니다."""
    try:
        text = fn()
    except ParseError as exc:
        text = f"⚠️ {exc}\n`/help` 에서 형식을 확인하세요."
    await interaction.response.send_message(text[:2000], ephemeral=True)


class AssistantBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()  # DM·멘션 내용은 특권 인텐트 없이도 읽힘
        super().__init__(intents=intents)
        # 서버에 초대해도, 내 계정에 '사용자 앱'으로 설치해도 DM에서 쓸 수 있게
        self.tree = GuardedTree(
            self,
            allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True),
            allowed_installs=app_commands.AppInstallationType(guild=True, user=True),
        )
        register_commands(self.tree)

    async def setup_hook(self) -> None:
        if settings.discord_guild_id:
            guild = discord.Object(id=settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        await self.tree.sync()
        self.reminder_loop.change_interval(seconds=settings.reminder_interval_seconds)
        self.reminder_loop.start()

    async def on_ready(self) -> None:
        log.info("Discord bot ready as %s (LLM=%s)", self.user, settings.llm_provider)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or self.user is None:
            return
        is_dm = isinstance(message.channel, discord.DMChannel)
        if not is_dm and self.user not in message.mentions:
            return  # 서버 채널에서는 @멘션했을 때만 반응
        if not is_allowed(message.author.id):
            return
        text = re.sub(rf"<@!?{self.user.id}>", "", message.content).strip()
        if not text:
            return
        async with message.channel.typing():
            reply = await self._chat(message.author.id, text)
        await message.reply(reply[:2000], mention_author=False)

    async def _chat(self, user_id: int, text: str) -> str:
        try:
            llm = get_llm()
        except LLMError as exc:
            return f"AI 설정이 아직 안 됐어요 ({exc}). 명령어는 `/help` 참고."
        with session_scope() as s:
            return await handle_message(llm, s, user_id, text, now())

    @tasks.loop(seconds=300)
    async def reminder_loop(self) -> None:
        for user_id, text in collect_messages(now()):
            try:
                user = self.get_user(user_id) or await self.fetch_user(user_id)
                await user.send(text)
            except discord.HTTPException:  # DM 차단 등. 한 건 실패가 나머지를 막지 않게
                log.exception("reminder DM failed (user %s)", user_id)

    @reminder_loop.before_loop
    async def _wait_ready(self) -> None:
        await self.wait_until_ready()


def register_commands(tree: app_commands.CommandTree) -> None:
    @tree.command(name="whoami", description="내 디스코드 사용자 ID 확인 (ALLOWED_USER_IDS 설정용)")
    async def whoami(i: discord.Interaction):
        await i.response.send_message(f"내 사용자 ID: `{i.user.id}`", ephemeral=True)

    @tree.command(name="help", description="사용법")
    async def help_(i: discord.Interaction):
        await _reply(i, lambda: cmd.HELP)

    @tree.command(name="class_add", description="시간표에 수업 추가")
    @app_commands.describe(weekday="요일", time="시간 (예: 09:00-10:15)", course="과목명", location="강의실")
    @app_commands.choices(weekday=WEEKDAY_CHOICES)
    async def class_add(i: discord.Interaction, weekday: app_commands.Choice[str], time: str, course: str,
                        location: str | None = None):
        await _reply(i, lambda: cmd.class_add(i.user.id, weekday.value, time, course, location))

    @tree.command(name="hw_add", description="과제 등록")
    @app_commands.describe(date="마감 날짜 (12/03, 내일 …)", course="과목명", title="과제 제목",
                           time="마감 시간 (기본 23:59)")
    async def hw_add(i: discord.Interaction, date: str, course: str, title: str, time: str | None = None):
        await _reply(i, lambda: cmd.hw_add(i.user.id, date, course, title, time))

    @tree.command(name="exam_add", description="시험 등록")
    @app_commands.describe(date="날짜", time="시작 시간 (예: 10:00)", course="과목명", title="예: 중간고사",
                           location="장소")
    async def exam_add(i: discord.Interaction, date: str, time: str, course: str, title: str | None = None,
                       location: str | None = None):
        await _reply(i, lambda: cmd.exam_add(i.user.id, date, time, course, title, location))

    @tree.command(name="today", description="오늘 수업·과제·시험")
    async def today(i: discord.Interaction):
        await _reply(i, lambda: cmd.day(i.user.id, 0))

    @tree.command(name="tomorrow", description="내일 수업·과제·시험")
    async def tomorrow(i: discord.Interaction):
        await _reply(i, lambda: cmd.day(i.user.id, 1))

    @tree.command(name="week", description="앞으로 7일 과제·시험")
    async def week(i: discord.Interaction):
        await _reply(i, lambda: cmd.week(i.user.id))

    @tree.command(name="hw", description="남은 과제 목록")
    async def hw(i: discord.Interaction):
        await _reply(i, lambda: cmd.hw_list(i.user.id))

    @tree.command(name="exams", description="예정된 시험 목록")
    async def exams(i: discord.Interaction):
        await _reply(i, lambda: cmd.exams(i.user.id))

    @tree.command(name="timetable", description="내 시간표")
    async def timetable(i: discord.Interaction):
        await _reply(i, lambda: cmd.timetable(i.user.id))

    @tree.command(name="done", description="과제 완료 표시")
    @app_commands.describe(id="과제 번호 (#3 이면 3)")
    async def done(i: discord.Interaction, id: int):
        await _reply(i, lambda: cmd.done(i.user.id, id))

    @tree.command(name="del", description="항목 삭제")
    @app_commands.describe(kind="종류", id="번호")
    @app_commands.choices(kind=KIND_CHOICES)
    async def delete(i: discord.Interaction, kind: app_commands.Choice[str], id: int):
        await _reply(i, lambda: cmd.delete(i.user.id, kind.value, id))
