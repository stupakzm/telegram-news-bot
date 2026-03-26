# bot/router.py
import logging
import time
from bot.commands import start, themes, schedule, upgrade, history, addtheme, settings, admin
from bot.commands import payments as payments_cmd
from bot.rate_limiter import check_rate_limit
import db.client as db
import bot.telegram as tg

logger = logging.getLogger(__name__)

COMMAND_MAP = {
    "/start": ("bot.commands.start", "handle"),
    "/themes": ("bot.commands.themes", "handle"),
    "/schedule": ("bot.commands.schedule", "handle"),
    # "/upgrade": ("bot.commands.upgrade", "handle"),  # disabled until Stars payments available
    "/history": ("bot.commands.history", "handle"),
    "/addtheme": ("bot.commands.addtheme", "handle_ai"),
    "/addthememanual": ("bot.commands.addtheme", "handle_manual"),
    "/settings": ("bot.commands.settings", "handle"),
    "/admin": ("bot.commands.admin", "handle"),
}


def _handle_callback(callback_query: dict) -> None:
    data = callback_query.get("data", "")
    user_id = callback_query["from"]["id"]

    if data.startswith("themes:add:"):
        _, _, theme_type, theme_id = data.split(":")
        themes.add_theme(user_id, theme_type, int(theme_id))
        msg = callback_query.get("message", {})
        themes.refresh_keyboard(user_id, msg["chat"]["id"], msg["message_id"])
    elif data.startswith("themes:remove:"):
        _, _, theme_type, theme_id = data.split(":")
        themes.remove_theme(user_id, theme_type, int(theme_id))
        msg = callback_query.get("message", {})
        themes.refresh_keyboard(user_id, msg["chat"]["id"], msg["message_id"])
    elif data.startswith("pay:"):
        tier = data.split(":", 1)[1]
        payments_cmd.send_invoice(user_id, tier)
    # elif data.startswith("upgrade:show"):  # disabled until Stars payments available
    #     upgrade.handle({"from": callback_query["from"], "chat": {"id": user_id}})
    elif data.startswith("addtheme:ai"):
        addtheme.handle_ai({"from": callback_query["from"], "chat": {"id": user_id}})
    elif data.startswith("addtheme:manual"):
        addtheme.handle_manual({"from": callback_query["from"], "chat": {"id": user_id}})
    elif data.startswith("addtheme:feed:"):
        idx = int(data.split(":")[2])
        addtheme.toggle_feed(user_id, idx)
    elif data == "addtheme:feeds_done":
        addtheme.feeds_done(user_id)
    elif data.startswith("schedule:day:"):
        day_idx = int(data.split(":")[2])
        schedule.toggle_day(user_id, day_idx)
    elif data == "schedule:days_done":
        schedule.days_done(user_id)
    elif data == "schedule:setup":
        schedule.handle({"from": callback_query["from"], "chat": {"id": user_id}})
    elif data == "themes:browse":
        themes.handle({"from": callback_query["from"], "chat": {"id": user_id}})
    elif data.startswith("reaction:"):
        parts = data.split(":", 2)
        if len(parts) == 3:
            reaction = parts[1]  # 'up' or 'down'
            article_url = parts[2]
            now_ts = int(time.time())
            db.execute_many([(
                "INSERT OR REPLACE INTO article_reactions "
                "(user_id, article_url, reaction, reacted_at) "
                "VALUES (?, ?, ?, ?)",
                [user_id, article_url, reaction, now_ts]
            )])
            emoji = "\U0001f44d" if reaction == "up" else "\U0001f44e"
            tg.answer_callback_query(callback_query["id"], text=f"{emoji} Noted!")
            return
    tg.answer_callback_query(callback_query["id"])


def _handle_pending_action(message: dict) -> bool:
    user_id = message["from"]["id"]
    rows = db.execute(
        "SELECT action, data FROM user_pending_actions WHERE user_id = ?", [user_id]
    )
    if not rows:
        return False
    action = rows[0]["action"]
    data_json = rows[0]["data"]
    if action.startswith("addtheme_"):
        addtheme.handle_pending(message, action, data_json)
    elif action.startswith("schedule_"):
        schedule.handle_pending(message, action, data_json)
    else:
        # Unknown pending action — clear it
        logger.warning("_handle_pending_action: unknown action %r for user %d", action, user_id)
        db.execute_many([("DELETE FROM user_pending_actions WHERE user_id = ?", [user_id])])
    return True


def handle_update(update: dict) -> None:
    """Route a Telegram update to the appropriate handler."""
    if "callback_query" in update:
        _handle_callback(update["callback_query"])
        return

    message = update.get("message", {})
    if not message:
        return

    if "successful_payment" in message:
        payments_cmd.handle_successful_payment(message)
        return

    text = message.get("text", "")
    if not text:
        return

    if not text.startswith("/"):
        if _handle_pending_action(message):
            return

    if text.startswith("/"):
        # Rate limit commands only (D-13, D-15)
        user_id = message["from"]["id"]
        chat_id = message["chat"]["id"]
        allowed, retry_after = check_rate_limit(user_id)
        if not allowed:
            tg.send_message(
                chat_id=chat_id,
                text=f"Slow down! You've sent too many commands. Try again in {retry_after} seconds.",
            )
            return

    command = text.split()[0].split("@")[0]
    entry = COMMAND_MAP.get(command)
    if entry:
        import importlib
        mod = importlib.import_module(entry[0])
        getattr(mod, entry[1])(message)
