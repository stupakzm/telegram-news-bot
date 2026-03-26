import json
import db.client as db
import bot.telegram as tg

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]  # index+1 = ISO weekday


def set_global_schedule(user_id: int, days: list[int], hour_utc: int) -> None:
    """Upsert the global (all-themes) schedule for a user."""
    db.execute_many([
        ("DELETE FROM user_schedules WHERE user_id = ? AND user_theme_id IS NULL", [user_id]),
        (
            "INSERT INTO user_schedules (user_id, user_theme_id, days, hour_utc) VALUES (?, NULL, ?, ?)",
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

    result = tg.send_message(chat_id=user_id, text=text, reply_markup={"inline_keyboard": day_buttons})
    import time as _time
    if result.get("message_id"):
        db.track_bot_message(user_id, result["message_id"])
    db.execute_many([
        (
            "INSERT OR REPLACE INTO user_pending_actions (user_id, action, data, created_at) "
            "VALUES (?, 'schedule_days', ?, ?)",
            [user_id, json.dumps({"selected": []}), int(_time.time())],
        )
    ])


def toggle_day(user_id: int, day_idx: int, chat_id: int, message_id: int) -> None:
    """Toggle a day in the pending schedule selection and update buttons in-place."""
    rows = db.execute(
        "SELECT data FROM user_pending_actions WHERE user_id = ? AND action = 'schedule_days'",
        [user_id],
    )
    if not rows:
        return
    data = json.loads(rows[0]["data"])
    selected: list = data.get("selected", [])
    if day_idx in selected:
        selected.remove(day_idx)
    else:
        selected.append(day_idx)
    data["selected"] = selected
    import time as _time
    db.execute_many([
        (
            "INSERT OR REPLACE INTO user_pending_actions (user_id, action, data, created_at) "
            "VALUES (?, 'schedule_days', ?, ?)",
            [user_id, json.dumps(data), int(_time.time())],
        )
    ])
    day_buttons = [
        [{"text": f"{'✅ ' if i + 1 in selected else ''}{day}", "callback_data": f"schedule:day:{i + 1}"}]
        for i, day in enumerate(DAYS)
    ]
    day_buttons.append([{"text": "✅ Done selecting days", "callback_data": "schedule:days_done"}])
    tg.edit_message_reply_markup(chat_id, message_id, {"inline_keyboard": day_buttons})


def days_done(user_id: int, chat_id: int, message_id: int) -> None:
    """User confirmed day selection — remove the form and ask for hour."""
    rows = db.execute(
        "SELECT data FROM user_pending_actions WHERE user_id = ? AND action = 'schedule_days'",
        [user_id],
    )
    if not rows:
        return
    data = json.loads(rows[0]["data"])
    selected = data.get("selected", [])
    if not selected:
        tg.send_message(chat_id=user_id, text="⚠️ Please select at least one day.")
        return
    # Transition to asking for hour
    import time as _time
    db.execute_many([
        (
            "INSERT OR REPLACE INTO user_pending_actions (user_id, action, data, created_at) "
            "VALUES (?, 'schedule_hour', ?, ?)",
            [user_id, json.dumps(data), int(_time.time())],
        )
    ])
    tg.delete_message(chat_id, message_id)
    result = tg.send_message(
        chat_id=user_id,
        text="What hour (UTC) should your digest be delivered? (0–23):",
    )
    if result.get("message_id"):
        db.track_bot_message(user_id, result["message_id"])


def handle_pending(message: dict, action: str, data_json: str) -> None:
    """Handle schedule multi-step pending actions."""
    user_id = message["from"]["id"]
    text = message.get("text", "").strip()
    data = json.loads(data_json or "{}")

    if action == "schedule_hour":
        try:
            hour = int(text)
            if not (0 <= hour <= 23):
                raise ValueError
        except ValueError:
            tg.send_message(chat_id=user_id, text="⚠️ Please send a number between 0 and 23.")
            return
        days = data.get("selected", [])
        set_global_schedule(user_id, days, hour)
        # Clear pending
        db.execute_many([("DELETE FROM user_pending_actions WHERE user_id = ?", [user_id])])
        day_names = [DAYS[d - 1] for d in days]
        result = tg.send_message(
            chat_id=user_id,
            text=f"✅ Schedule set: {', '.join(day_names)} at {hour:02d}:00 UTC.",
        )
        if result.get("message_id"):
            db.track_bot_message(user_id, result["message_id"])
