# bot/router.py
from bot.commands import start, themes, schedule, upgrade, history, addtheme, settings
from bot.commands import payments as payments_cmd
import db.client as db

COMMAND_MAP = {
    "/start": ("bot.commands.start", "handle"),
    "/themes": ("bot.commands.themes", "handle"),
    "/schedule": ("bot.commands.schedule", "handle"),
    "/upgrade": ("bot.commands.upgrade", "handle"),
    "/history": ("bot.commands.history", "handle"),
    "/addtheme": ("bot.commands.addtheme", "handle_ai"),
    "/addthememanual": ("bot.commands.addtheme", "handle_manual"),
    "/settings": ("bot.commands.settings", "handle"),
}


def _handle_callback(callback_query: dict) -> None:
    data = callback_query.get("data", "")
    user_id = callback_query["from"]["id"]
    message = callback_query.get("message", {})

    if data.startswith("themes:add:"):
        _, _, theme_type, theme_id = data.split(":")
        themes.add_theme(user_id, theme_type, int(theme_id))
    elif data.startswith("themes:remove:"):
        _, _, theme_type, theme_id = data.split(":")
        themes.remove_theme(user_id, theme_type, int(theme_id))
    elif data.startswith("pay:"):
        tier = data.split(":")[1]
        payments_cmd.send_invoice(user_id, tier)
    elif data.startswith("upgrade:show"):
        upgrade.handle({"from": callback_query["from"], "chat": {"id": user_id}})
    elif data.startswith("addtheme:ai"):
        addtheme.handle_ai({"from": callback_query["from"], "chat": {"id": user_id}})
    elif data.startswith("addtheme:manual"):
        addtheme.handle_manual({"from": callback_query["from"], "chat": {"id": user_id}})
    elif data.startswith("addtheme:feed:"):
        idx = int(data.split(":")[2])
        addtheme.toggle_feed(user_id, idx)
    elif data == "addtheme:feeds_done":
        addtheme.feeds_done(user_id)
    import bot.telegram as tg
    tg.answer_callback_query(callback_query["id"])


def _handle_pending_action(message: dict) -> bool:
    user_id = message["from"]["id"]
    rows = db.execute(
        "SELECT action, data FROM user_pending_actions WHERE user_id = ?", [user_id]
    )
    if not rows:
        return False
    addtheme.handle_pending(message, rows[0]["action"], rows[0]["data"])
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

    command = text.split()[0].split("@")[0]
    entry = COMMAND_MAP.get(command)
    if entry:
        import importlib
        mod = importlib.import_module(entry[0])
        getattr(mod, entry[1])(message)
