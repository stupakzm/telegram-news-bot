import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import db.client as db
import bot.telegram as tg
from delivery.scheduler import TIER_HOURS

_QUICK_PICKS = [
    ("UTC", "UTC"),
    ("Europe/Kyiv", "Europe/Kyiv"),
    ("Europe/London", "Europe/London"),
    ("America/New_York", "America/New_York"),
    ("America/Los_Angeles", "America/Los_Angeles"),
    ("Asia/Tokyo", "Asia/Tokyo"),
]


def _user(user_id: int) -> dict | None:
    rows = db.execute("SELECT tier, timezone FROM users WHERE user_id = ?", [user_id])
    return rows[0] if rows else None


def _schedule_line(tier: str, tz_name: str) -> str:
    hours = TIER_HOURS.get(tier, ())
    if not hours:
        return "_No deliveries — your plan is expired._"
    formatted = ", ".join(f"{h:02d}:00" for h in hours)
    label = "Trial (VIP)" if tier == "trial" else tier.upper()
    return f"{label} schedule: *{formatted}* ({tz_name})"


def _build_view(user: dict) -> tuple[str, dict]:
    tz_name = user["timezone"] or "UTC"
    tier = user["tier"]

    text = (
        "🌍 *Your Timezone*\n\n"
        f"Current: *{tz_name}*\n"
        f"{_schedule_line(tier, tz_name)}\n\n"
        "Pick a quick option or tap *Type custom* to enter an IANA timezone name "
        "(e.g. `Europe/Berlin`, `Asia/Singapore`)."
    )

    buttons = [
        [{"text": f"📍 {label}", "callback_data": f"tz:set:{value}"}]
        for label, value in _QUICK_PICKS
    ]
    buttons.append([{"text": "⌨️ Type custom", "callback_data": "tz:custom"}])
    return text, {"inline_keyboard": buttons}


def handle(message: dict) -> None:
    user_id = message["from"]["id"]
    chat_id = message["chat"]["id"]
    user = _user(user_id)
    if not user:
        tg.send_message(chat_id=chat_id, text="Please /start the bot first.")
        return
    text, markup = _build_view(user)
    result = tg.send_message(chat_id=chat_id, text=text, reply_markup=markup)
    if result.get("message_id"):
        db.track_bot_message(user_id, result["message_id"])


def _save_timezone(user_id: int, tz_name: str) -> bool:
    try:
        ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return False
    db.execute_many([(
        "UPDATE users SET timezone = ? WHERE user_id = ?",
        [tz_name, user_id],
    )])
    return True


def handle_set_callback(callback_query: dict, tz_name: str) -> None:
    user_id = callback_query["from"]["id"]
    msg = callback_query.get("message", {})
    chat_id = msg.get("chat", {}).get("id", user_id)

    if not _save_timezone(user_id, tz_name):
        tg.answer_callback_query(callback_query["id"], text="Unknown timezone.")
        return
    tg.answer_callback_query(callback_query["id"], text=f"Set to {tz_name}")
    user = _user(user_id)
    text = (
        f"✅ Timezone set to *{tz_name}*.\n\n"
        f"{_schedule_line(user['tier'], tz_name)}"
    )
    result = tg.send_message(chat_id=chat_id, text=text)
    if result.get("message_id"):
        db.track_bot_message(user_id, result["message_id"])


def handle_custom_callback(callback_query: dict) -> None:
    user_id = callback_query["from"]["id"]
    msg = callback_query.get("message", {})
    chat_id = msg.get("chat", {}).get("id", user_id)

    db.execute_many([(
        "INSERT OR REPLACE INTO user_pending_actions (user_id, action, data, created_at) "
        "VALUES (?, 'timezone_set', '{}', ?)",
        [user_id, int(time.time())],
    )])
    tg.answer_callback_query(callback_query["id"])
    result = tg.send_message(
        chat_id=chat_id,
        text=(
            "Send an IANA timezone name.\n"
            "_Examples:_ `Europe/Berlin`, `Asia/Singapore`, `Australia/Sydney`\n\n"
            "Full list: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones"
        ),
    )
    if result.get("message_id"):
        db.track_bot_message(user_id, result["message_id"])


def handle_pending(message: dict, action: str, data_json: str) -> None:
    user_id = message["from"]["id"]
    chat_id = message["chat"]["id"]
    text = (message.get("text", "") or "").strip()

    if action != "timezone_set":
        return

    if not _save_timezone(user_id, text):
        tg.send_message(
            chat_id=chat_id,
            text="⚠️ That's not a valid IANA timezone. Try again or send /timezone to start over.",
        )
        return

    db.execute_many([("DELETE FROM user_pending_actions WHERE user_id = ?", [user_id])])
    user = _user(user_id)
    confirm = (
        f"✅ Timezone set to *{text}*.\n\n"
        f"{_schedule_line(user['tier'], text)}"
    )
    result = tg.send_message(chat_id=chat_id, text=confirm)
    if result.get("message_id"):
        db.track_bot_message(user_id, result["message_id"])
