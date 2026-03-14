# bot/commands/settings.py
import json
from datetime import datetime, timezone
import db.client as db
import bot.telegram as tg


def handle(message: dict) -> None:
    user_id = message["from"]["id"]

    user = db.execute("SELECT tier, tier_expires_at FROM users WHERE user_id = ?", [user_id])
    if not user:
        tg.send_message(chat_id=user_id, text="Please /start the bot first.")
        return

    tier = user[0]["tier"]
    expires = user[0]["tier_expires_at"]

    themes = db.execute(
        """
        SELECT ut.theme_type, ut.theme_id, ut.articles_per_theme,
               t.name as default_name, ct.name as custom_name
        FROM user_themes ut
        LEFT JOIN themes t ON ut.theme_type = 'default' AND t.id = ut.theme_id
        LEFT JOIN custom_themes ct ON ut.theme_type = 'custom' AND ct.id = ut.theme_id
        WHERE ut.user_id = ?
        """,
        [user_id],
    )

    schedules = db.execute(
        "SELECT days, hour_utc, user_theme_id FROM user_schedules WHERE user_id = ?",
        [user_id],
    )

    tier_label = {"free": "Free", "one_time": "One-time", "monthly": "Monthly"}.get(tier, tier)
    if tier == "monthly" and expires:
        exp_dt = datetime.fromtimestamp(expires, tz=timezone.utc).strftime("%b %d, %Y")
        tier_label += f" (renews {exp_dt})"

    theme_lines = []
    for t in themes:
        name = t["default_name"] or t["custom_name"] or "?"
        tag = "(custom)" if t["theme_type"] == "custom" else ""
        theme_lines.append(f"  • {name} {tag} — {t['articles_per_theme']} article(s)/delivery")

    schedule_lines = []
    for s in schedules:
        days = json.loads(s["days"])
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        day_str = ", ".join(day_names[d - 1] for d in days)
        scope = "All themes" if s["user_theme_id"] is None else f"Theme {s['user_theme_id']}"
        schedule_lines.append(f"  • {scope}: {day_str} at {s['hour_utc']:02d}:00 UTC")

    text = (
        f"⚙️ *Your Settings*\n\n"
        f"*Plan:* {tier_label}\n\n"
        f"*Themes ({len(themes)}):*\n" + ("\n".join(theme_lines) or "  None set") + "\n\n"
        f"*Schedule:*\n" + ("\n".join(schedule_lines) or "  None set")
    )

    buttons = [
        [{"text": "📰 Manage Themes", "callback_data": "themes:browse"}],
        [{"text": "⏰ Change Schedule", "callback_data": "schedule:setup"}],
    ]
    if tier == "free":
        buttons.append([{"text": "⭐ Upgrade Plan", "callback_data": "upgrade:show"}])

    tg.send_message(chat_id=user_id, text=text, reply_markup={"inline_keyboard": buttons})
