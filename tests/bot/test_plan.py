import os
import time
from unittest.mock import patch

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("STARS_VIP_PRICE", "100")
os.environ.setdefault("STARS_SVIP_PRICE", "290")


def _msg(user_id=1):
    return {"from": {"id": user_id}, "chat": {"id": user_id}}


def _user(tier, expires=None, timezone="UTC"):
    return {"tier": tier, "tier_expires_at": expires, "timezone": timezone}


@patch("bot.commands.plan.tg.send_message")
@patch("bot.commands.plan._user")
def test_plan_unknown_user_prompts_start(mock_user, mock_send):
    mock_user.return_value = None
    from bot.commands.plan import handle
    handle(_msg())
    text = mock_send.call_args[1].get("text", "")
    assert "/start" in text


@patch("bot.commands.plan.tg.send_message")
@patch("bot.commands.plan._user")
def test_plan_trial_shows_activate_buttons(mock_user, mock_send):
    future = int(time.time()) + 86400
    mock_user.return_value = _user("trial", future)
    from bot.commands.plan import handle
    handle(_msg())
    markup = mock_send.call_args[1]["reply_markup"]
    btns = [b[0]["callback_data"] for b in markup["inline_keyboard"]]
    assert btns == ["pay:vip", "pay:svip"]
    labels = [b[0]["text"] for b in markup["inline_keyboard"]]
    assert all("Activate" in l for l in labels)


@patch("bot.commands.plan.tg.send_message")
@patch("bot.commands.plan._user")
def test_plan_vip_shows_renew_and_switch_to_svip(mock_user, mock_send):
    future = int(time.time()) + 86400
    mock_user.return_value = _user("vip", future)
    from bot.commands.plan import handle
    handle(_msg())
    markup = mock_send.call_args[1]["reply_markup"]
    labels = [b[0]["text"] for b in markup["inline_keyboard"]]
    assert any("Renew VIP" in l for l in labels)
    assert any("Switch to SVIP" in l for l in labels)


@patch("bot.commands.plan.tg.send_message")
@patch("bot.commands.plan._user")
def test_plan_svip_shows_renew_and_switch_to_vip(mock_user, mock_send):
    future = int(time.time()) + 86400
    mock_user.return_value = _user("svip", future)
    from bot.commands.plan import handle
    handle(_msg())
    markup = mock_send.call_args[1]["reply_markup"]
    labels = [b[0]["text"] for b in markup["inline_keyboard"]]
    assert any("Renew SVIP" in l for l in labels)
    assert any("Switch to VIP" in l for l in labels)


@patch("bot.commands.plan.tg.send_message")
@patch("bot.commands.plan.db.execute_many")
@patch("bot.commands.plan._user")
def test_plan_auto_expires_past_plan(mock_user, mock_execute_many, mock_send):
    past = int(time.time()) - 86400
    mock_user.return_value = _user("vip", past)
    from bot.commands.plan import handle
    handle(_msg())
    # Should have issued an UPDATE to expired
    sql, args = mock_execute_many.call_args[0][0][0]
    assert "tier = 'expired'" in sql
    # After expire, the rendered view should show Activate buttons
    markup = mock_send.call_args[1]["reply_markup"]
    labels = [b[0]["text"] for b in markup["inline_keyboard"]]
    assert all("Activate" in l for l in labels)


@patch("bot.commands.plan.tg.send_message")
@patch("bot.commands.plan._user")
def test_plan_expired_text_mentions_expired(mock_user, mock_send):
    mock_user.return_value = _user("expired", None)
    from bot.commands.plan import handle
    handle(_msg())
    text = mock_send.call_args[1].get("text", "")
    assert "expired" in text.lower()
