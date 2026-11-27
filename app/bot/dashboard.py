"""버튼 대시보드: 고정 메시지의 버튼을 누르면 나에게만 보이는 답이 옵니다.

버튼은 봇이 재시작돼도 계속 동작하도록 custom_id 를 고정한 '영구 View' 입니다.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

import discord

from app.bot import commands as cmd
from app.campus import landscape_curriculum as cur
from app.campus import lauos_notice, uos_meal
from app.campus_alerts import calendar_text, has_calendar, refresh_calendar
from app.clock import now
from app.config import settings
from app.parsing import ParseError

log = logging.getLogger(__name__)

DASHBOARD_TEXT = """## 🏫 학교생활 대시보드
버튼을 누르면 **나에게만 보이는** 답이 와요.

🍚 **학식** 식당 골라서 오늘 메뉴
📢 **공지** 조경학과 홈페이지 최근 공지
📅 **학사일정** 앞으로 45일 일정
📝 **과제** 남은 과제 · ➕ **과제 추가**
🎓 **졸업요건** 들은 과목 입력 → 남은 학점·안 들은 전공 과목

새 학과 공지와 수강신청·장학금·휴복학 일정(7일 전·전날)은 #알림 채널로 와요."""


def _allowed(user_id: int) -> bool:
    return not settings.allowed_user_ids or user_id in settings.allowed_user_ids


class GuardedView(discord.ui.View):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if _allowed(interaction.user.id):
            return True
        await interaction.response.send_message(
            f"허용되지 않은 사용자예요. ALLOWED_USER_IDS 에 {interaction.user.id} 를 추가하세요.", ephemeral=True)
        return False


async def _answer(interaction: discord.Interaction, fn: Callable[[], str], view: discord.ui.View | None = None):
    try:
        text = fn()
    except ParseError as exc:
        text = f"⚠️ {exc}"
    kwargs = {"view": view} if view is not None else {}
    if interaction.response.is_done():
        await interaction.followup.send(text[:2000], ephemeral=True, **kwargs)
    else:
        await interaction.response.send_message(text[:2000], ephemeral=True, **kwargs)


class DashboardView(GuardedView):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="학식", emoji="🍚", style=discord.ButtonStyle.primary, custom_id="dash:meal", row=0)
    async def meal(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_message("어느 식당이요?", view=MealView(), ephemeral=True)

    @discord.ui.button(label="공지", emoji="📢", style=discord.ButtonStyle.secondary, custom_id="dash:notice", row=0)
    async def notice(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            text = lauos_notice.format_notices(await lauos_notice.fetch_notices())
        except Exception:  # 학과 홈페이지 장애 등
            log.exception("notice fetch failed")
            text = f"학과 홈페이지에 접속하지 못했어요. 직접 보기: <{lauos_notice.LIST_URL}>"
        await interaction.followup.send(text[:2000], ephemeral=True)

    @discord.ui.button(label="학사일정", emoji="📅", style=discord.ButtonStyle.secondary, custom_id="dash:cal", row=0)
    async def calendar(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        today = now().date()
        if not has_calendar(today):
            try:
                await refresh_calendar(today)
            except Exception:
                log.exception("calendar fetch failed")
        await interaction.followup.send(calendar_text(today)[:2000], ephemeral=True)

    @discord.ui.button(label="과제", emoji="📝", style=discord.ButtonStyle.secondary, custom_id="dash:hw", row=1)
    async def hw(self, interaction: discord.Interaction, _: discord.ui.Button):
        await _answer(interaction, lambda: cmd.hw_list(interaction.user.id))

    @discord.ui.button(label="과제 추가", emoji="➕", style=discord.ButtonStyle.success, custom_id="dash:hw_add", row=1)
    async def hw_add(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(HomeworkModal())

    @discord.ui.button(label="졸업요건", emoji="🎓", style=discord.ButtonStyle.secondary, custom_id="dash:grad", row=1)
    async def grad(self, interaction: discord.Interaction, _: discord.ui.Button):
        await _answer(interaction, lambda: cmd.grad_summary(interaction.user.id), view=GradView())


# ---------- 학식 ----------
class MealSelect(discord.ui.Select):
    def __init__(self) -> None:
        super().__init__(placeholder="식당 고르기", options=[
            discord.SelectOption(label=name, value=code) for code, name in uos_meal.RESTAURANTS.items()])

    async def callback(self, interaction: discord.Interaction):
        code = self.values[0]
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            text = uos_meal.format_menu(await uos_meal.fetch_day_menu(now().date(), code))
        except Exception:
            log.exception("meal fetch failed")
            text = "학교 홈페이지에 접속하지 못했어요. 잠시 뒤 다시 눌러 주세요."
        await interaction.followup.send(text[:2000], ephemeral=True)


class MealView(GuardedView):
    def __init__(self) -> None:
        super().__init__(timeout=300)
        self.add_item(MealSelect())


# ---------- 과제 추가 ----------
class HomeworkModal(discord.ui.Modal, title="과제 추가"):
    course = discord.ui.TextInput(label="과목", placeholder="예: 조경계획", max_length=100)
    hw_title = discord.ui.TextInput(label="과제 제목", placeholder="예: 대상지 분석 보고서", max_length=200)
    due_date = discord.ui.TextInput(label="마감 날짜", placeholder="12/03, 내일, 모레, 2026-12-03", max_length=20)
    due_time = discord.ui.TextInput(label="마감 시간 (비우면 23:59)", placeholder="18:00", required=False,
                                    max_length=10)

    async def on_submit(self, interaction: discord.Interaction):
        await _answer(interaction, lambda: cmd.hw_add(
            interaction.user.id, self.due_date.value, self.course.value, self.hw_title.value,
            self.due_time.value or None))


# ---------- 졸업요건 ----------
class CourseModal(discord.ui.Modal, title="들은 과목 직접 입력"):
    name = discord.ui.TextInput(label="과목 이름", placeholder="예: 대학영어", max_length=100)
    credits = discord.ui.TextInput(label="학점 (비우면 3)", placeholder="3", required=False, max_length=2)
    category = discord.ui.TextInput(label="구분 (전필/전선/교필/교선/일선)", placeholder="비우면 자동", required=False,
                                    max_length=10)

    async def on_submit(self, interaction: discord.Interaction):
        await _answer(interaction, lambda: cmd.grad_add(
            interaction.user.id, self.name.value, self.credits.value, self.category.value))


class CurriculumSelect(discord.ui.Select):
    def __init__(self, years: tuple[int, ...]) -> None:
        options = [discord.SelectOption(label=c[:100], value=c[:100], description=f"{y}학년")
                   for y in years for c in cur.CURRICULUM[y]][:25]
        super().__init__(placeholder=f"{'·'.join(map(str, years))}학년 전공 과목 (여러 개 선택)",
                         min_values=1, max_values=len(options), options=options)

    async def callback(self, interaction: discord.Interaction):
        await _answer(interaction, lambda: cmd.grad_quick_add(interaction.user.id, list(self.values)))


class CurriculumView(GuardedView):
    def __init__(self) -> None:
        super().__init__(timeout=600)
        self.add_item(CurriculumSelect((1, 2)))
        self.add_item(CurriculumSelect((3, 4)))


class DeleteCourseSelect(discord.ui.Select):
    def __init__(self, courses) -> None:
        options = [discord.SelectOption(label=f"{c.name} ({c.credits}학점)"[:100], value=str(c.id),
                                        description=c.category) for c in courses[-25:]]
        super().__init__(placeholder="지울 과목 고르기", min_values=1, max_values=len(options), options=options)

    async def callback(self, interaction: discord.Interaction):
        await _answer(interaction, lambda: cmd.grad_delete(interaction.user.id, [int(v) for v in self.values]))


class GradView(GuardedView):
    def __init__(self) -> None:
        super().__init__(timeout=600)

    @discord.ui.button(label="전공 과목 고르기", emoji="📚", style=discord.ButtonStyle.primary)
    async def pick(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_message("들은 과목을 골라 주세요.", view=CurriculumView(), ephemeral=True)

    @discord.ui.button(label="직접 입력", emoji="✏️", style=discord.ButtonStyle.secondary)
    async def manual(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(CourseModal())

    @discord.ui.button(label="과목 삭제", emoji="🗑", style=discord.ButtonStyle.danger)
    async def remove(self, interaction: discord.Interaction, _: discord.ui.Button):
        from app import repository as repo
        from app.db import session_scope

        with session_scope() as s:
            courses = repo.list_completed_courses(s, interaction.user.id)
        if not courses:
            await interaction.response.send_message("입력한 과목이 없어요.", ephemeral=True)
            return
        view = GuardedView(timeout=300)
        view.add_item(DeleteCourseSelect(courses))
        extra = "\n(최근 25개 중에서만 고를 수 있어요)" if len(courses) > 25 else ""
        await interaction.response.send_message("지울 과목을 골라 주세요." + extra, view=view, ephemeral=True)

    @discord.ui.button(label="새로고침", emoji="🔄", style=discord.ButtonStyle.secondary)
    async def refresh(self, interaction: discord.Interaction, _: discord.ui.Button):
        await _answer(interaction, lambda: cmd.grad_summary(interaction.user.id), view=GradView())
