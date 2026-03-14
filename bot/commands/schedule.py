import json
import db.client as db
import bot.telegram as tg

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]  # index+1 = ISO weekday


def set_global_schedule(user_id: int, days: list[int], hour_utc: int) -> None:
    """Upsert the global (all-themes) schedule for a user."""
    db.execute_many([
        (
            "INSERT OR REPLACE INTO user_schedules (user_id, user_theme_id, days, hour_utc) VALUES (?, NULL, ?, ?)",
            [user_id, json.dumps(days), hour_utc],
        ),
    ])


def set_theme_schedule(user_id: int, user_theme_id: int, days: list[int], hour_utc: int) -> None:
    """Upsert a per-theme schedule for a paid user."""
    db.execute_many([
        ("DELETE FROM user_schedules WHERE user_id = ? AND user_theme_id = ?",
         [user_id, user_theme_id]),
        (
            "INSERT INTO user_schedules (user_id, user_theme_id, days, hour_utc) VALUES (?, ?, ?, ?)",
            [user_id, user_theme_id, json.dumps(days), hour_utc],
        ),
    ])


def handle(message: dict) -> None:
    user_id = message["from"]["id"]
    rows = db.execute("SELECT tier FROM users WHERE user_id = ?", [user_id])
    tier = rows[0]["tier"] if rows else "free"

    day_buttons = [
        [{"text": day, "callback_data": f"schedule:day:{i + 1}"}]
        for i, day in enumerate(DAYS)
    ]
    day_buttons.append([{"text": "✅ Done selecting days", "callback_data": "schedule:days_done"}])

    text = (
        "⏰ *Set Your Schedule*\n\n"
        "Select the days you want to receive your digest.\n"
        "_(Tap multiple, then tap Done)_"
    )
    if tier in ("one_time", "monthly"):
        text += "\n\n💡 _You can also set per-theme schedules after this._"

    tg.send_message(chat_id=user_id, text=text, reply_markup={"inline_keyboard": day_buttons})
