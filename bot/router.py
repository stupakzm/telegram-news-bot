# bot/router.py
import hashlib
import importlib
import logging
import time

import db.client as db
import bot.telegram as tg
from bot.commands import start, keywords, addurl, settings, admin, clear
from bot.commands import timezone as timezone_cmd
from bot.commands import payments as payments_cmd
from bot.rate_limiter import check_rate_limit

logger = logging.getLogger(__name__)

COMMAND_MAP = {
    "/start": ("bot.commands.start", "handle"),
    "/help": ("bot.commands.help", "handle"),
    "/keywords": ("bot.commands.keywords", "handle"),
    "/addurl": ("bot.commands.addurl", "handle"),
    "/settings": ("bot.commands.settings", "handle"),
    "/timezone": ("bot.commands.timezone", "handle"),
    "/plan": ("bot.commands.plan", "handle"),
    "/clear": ("bot.commands.clear", "handle"),
    "/admin": ("bot.commands.admin", "handle"),
}


def _handle_reaction(callback_query: dict, reaction: str, url_key: str) -> None:
    user_id = callback_query["from"]["id"]
    rows = db.execute(
        "SELECT article_url FROM delivery_log WHERE user_id = ? ORDER BY sent_at DESC LIMIT 200",
        [user_id],
    )
    article_url = next(
        (r["article_url"] for r in rows
         if hashlib.md5(r["article_url"].encode()).hexdigest()[:16] == url_key),
        None,
    )
    if article_url:
        db.execute_many([(
            "INSERT OR REPLACE INTO article_reactions "
            "(user_id, article_url, reaction, reacted_at) VALUES (?, ?, ?, ?)",
            [user_id, article_url, reaction, int(time.time())],
        )])
    emoji = "\U0001f44d" if reaction == "up" else "\U0001f44e"
    tg.answer_callback_query(callback_query["id"], text=f"{emoji} Noted!")


def _handle_callback(callback_query: dict) -> None:
    data = callback_query.get("data", "")

    if data.startswith("start:pack:"):
        pack_id = int(data.split(":")[2])
        start.handle_pack_callback(callback_query, pack_id)
        return
    if data == "start:skip":
        start.handle_skip_callback(callback_query)
        return

    if data == "kw:add":
        keywords.handle_add_callback(callback_query)
        return
    if data.startswith("kw:rm:"):
        idx = int(data.split(":")[2])
        keywords.handle_remove_callback(callback_query, idx)
        return

    if data == "url:add":
        addurl.handle_add_callback(callback_query)
        return
    if data.startswith("url:rm:"):
        feed_id = int(data.split(":")[2])
        addurl.handle_remove_callback(callback_query, feed_id)
        return

    if data.startswith("tz:set:"):
        tz_name = data.split(":", 2)[2]
        timezone_cmd.handle_set_callback(callback_query, tz_name)
        return
    if data == "tz:custom":
        timezone_cmd.handle_custom_callback(callback_query)
        return

    if data.startswith("pay:"):
        tier = data.split(":", 1)[1]
        payments_cmd.send_invoice(user_id=callback_query["from"]["id"], tier=tier)
        tg.answer_callback_query(callback_query["id"])
        return

    if data == "admin:refresh":
        admin.handle_refresh(callback_query)
        return

    if data.startswith("reaction:"):
        parts = data.split(":", 2)
        if len(parts) == 3:
            _handle_reaction(callback_query, parts[1], parts[2])
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

    if action.startswith("keywords_"):
        keywords.handle_pending(message, action, data_json)
    elif action.startswith("addurl_"):
        addurl.handle_pending(message, action, data_json)
    elif action.startswith("timezone_"):
        timezone_cmd.handle_pending(message, action, data_json)
    else:
        logger.warning("_handle_pending_action: unknown action %r for user %d", action, user_id)
        db.execute_many([("DELETE FROM user_pending_actions WHERE user_id = ?", [user_id])])
    return True


def handle_update(update: dict) -> None:
    if "callback_query" in update:
        _handle_callback(update["callback_query"])
        return

    if "pre_checkout_query" in update:
        # Telegram gives us 10 seconds to confirm before it cancels the charge.
        # We always confirm — the invoice payload was constructed by us, and
        # tier validation happens on successful_payment.
        pcq = update["pre_checkout_query"]
        tg.answer_pre_checkout_query(pcq["id"], ok=True)
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
        return

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
        mod = importlib.import_module(entry[0])
        getattr(mod, entry[1])(message)
