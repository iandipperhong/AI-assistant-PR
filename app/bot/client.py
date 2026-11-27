"""디스코드 봇: 슬래시 명령어, 자연어 메시지, DM 알림, 버튼 대시보드, #알림 채널 (학과 공지·학사일정)."""
from __future__ import annotations

import logging
import re
from collections.abc import Callable

import discord
from discord import app_commands
from discord.ext import tasks

from app import repository as repo
from app.assistant import handle_message
from app.bot import commands as cmd
from app.bot.dashboard import DASHBOARD_TEXT, DashboardView
from app.campus import lauos_notice
from app.campus_alerts import calendar_alert_messages, new_notice_messages, refresh_calendar
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
        self._dashboard_ready = False
        self._calendar_refreshed_on = None

    async def setup_hook(self) -> None:
        self.add_view(DashboardView())  # 재시작 뒤에도 고정 메시지의 버튼이 동작하게
        if settings.discord_guild_id:
            guild = discord.Object(id=settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        await self.tree.sync()
        self.reminder_loop.change_interval(seconds=settings.reminder_interval_seconds)
        self.reminder_loop.start()
        if settings.alert_channel_id:
            self.notice_loop.change_interval(minutes=settings.notice_check_minutes)
            self.notice_loop.start()
        self.calendar_loop.start()  # 학사일정은 대시보드 버튼에도 쓰여서 알림 채널이 없어도 새로고침

    async def on_ready(self) -> None:
        log.info("Discord bot ready as %s (LLM=%s)", self.user, settings.llm_provider)
        if settings.dashboard_channel_id and not self._dashboard_ready:
            self._dashboard_ready = True
            try:
                await self.ensure_dashboard()
            except discord.HTTPException:
                log.exception("dashboard setup failed")

    async def _channel(self, channel_id: int):
        return self.get_channel(channel_id) or await self.fetch_channel(channel_id)

    async def ensure_dashboard(self) -> None:
        """#대시보드 채널에 버튼 메시지를 하나 두고 고정. 이미 있으면 내용만 최신으로 고칩니다."""
        channel = await self._channel(settings.dashboard_channel_id)
        with session_scope() as s:
            saved = repo.get_value(s, "dashboard_message_id")
        if saved:
            try:
                msg = await channel.fetch_message(int(saved))
                await msg.edit(content=DASHBOARD_TEXT, view=DashboardView())
                return
            except discord.NotFound:
                pass
        msg = await channel.send(DASHBOARD_TEXT, view=DashboardView())
        with session_scope() as s:
            repo.set_value(s, "dashboard_message_id", str(msg.id))
        try:
            await msg.pin()
        except discord.HTTPException:
            log.warning("대시보드 메시지를 고정하지 못했어요. 봇에 '메시지 고정' 권한을 주세요.")

    def _mentions_me(self, message: discord.Message) -> bool:
        """봇 사용자 멘션, 또는 봇 이름과 같은 '봇 전용 역할' 멘션(@Assistant AI 가 역할로 잡히는 경우)."""
        if self.user in message.mentions:
            return True
        return any(r.tags is not None and r.tags.bot_id == self.user.id for r in message.role_mentions)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or self.user is None:
            return
        is_dm = isinstance(message.channel, discord.DMChannel)
        if not is_dm and not self._mentions_me(message):
            return  # 서버 채널에서는 @멘션했을 때만 반응
        if not is_allowed(message.author.id):
            log.info("허용되지 않은 사용자 메시지 무시: %s", message.author.id)
            await message.reply(f"허용되지 않은 사용자예요. ALLOWED_USER_IDS 에 {message.author.id} 를 추가하세요.",
                                mention_author=False)
            return
        text = re.sub(rf"<@!?{self.user.id}>|<@&\d+>", "", message.content).strip()
        if not text:
            # 역할 멘션은 디스코드가 메시지 내용을 봇에게 안 보여줌 (Message Content 권한 없을 때)
            log.info("멘션은 됐지만 내용이 비어 있음 (역할 멘션일 가능성): %s", message.content[:50])
            await message.reply(
                "메시지 내용을 읽지 못했어요 😢\n"
                "`@` 를 치고 목록에서 **역할이 아닌 봇(앱 표시가 있는 것)** 을 골라 멘션하거나, 저에게 DM 으로 보내 주세요.",
                mention_author=False)
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

    async def _post_alerts(self, texts: list[str]) -> None:
        if not texts or not settings.alert_channel_id:
            return
        channel = await self._channel(settings.alert_channel_id)
        for text in texts:
            await channel.send(text[:2000])

    @tasks.loop(minutes=30)
    async def notice_loop(self) -> None:
        try:
            notices = await lauos_notice.fetch_notices()
            await self._post_alerts(new_notice_messages(notices, now()))
        except Exception:  # 홈페이지 장애가 봇을 멈추지 않게
            log.exception("notice check failed")

    @tasks.loop(hours=1)
    async def calendar_loop(self) -> None:
        at = now()
        try:
            if self._calendar_refreshed_on != at.date():
                count = await refresh_calendar(at.date())
                self._calendar_refreshed_on = at.date()
                log.info("학사일정 %d건 새로고침", count)
        except Exception:
            log.exception("calendar refresh failed")
        if not settings.alert_channel_id:
            return
        try:
            await self._post_alerts(calendar_alert_messages(at))
        except Exception:
            log.exception("calendar alert failed")

    notice_loop.before_loop(_wait_ready)
    calendar_loop.before_loop(_wait_ready)


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
