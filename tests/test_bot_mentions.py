from types import SimpleNamespace

from app.bot.client import AssistantBot


def _bot():
    bot = AssistantBot.__new__(AssistantBot)  # 디스코드 연결 없이 메서드만 시험
    bot._connection = SimpleNamespace(user=SimpleNamespace(id=42))
    return bot


def test_mentions_me_user_and_bot_role():
    bot = _bot()
    me = bot.user
    other_role = SimpleNamespace(tags=None)
    bot_role = SimpleNamespace(tags=SimpleNamespace(bot_id=42))
    assert bot._mentions_me(SimpleNamespace(mentions=[me], role_mentions=[]))
    assert bot._mentions_me(SimpleNamespace(mentions=[], role_mentions=[bot_role]))
    assert not bot._mentions_me(SimpleNamespace(mentions=[], role_mentions=[other_role]))
