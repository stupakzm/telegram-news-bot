# bot/commands/upgrade.py
import os
import db.client as db
import bot.telegram as tg

COMPARISON = """\
⭐ *NewsBot Plans*

*Free*
• Up to 5 themes
• 1 article per theme
• One shared schedule

*One-time ({onetime} Stars)*
• Up to 6 themes
• 1 custom theme
• Per-theme schedules

*Monthly ({monthly} Stars/month)*
• Up to 9 themes
• Up to 3 custom themes
• 1–2 articles per theme
• Digest history (/history)
• Per-theme custom schedules
"""


def handle(message: dict) -> None:
    user_id = message["from"]["id"]
    rows = db.execute("SELECT tier FROM users WHERE user_id = ?", [user_id])
    tier = rows[0]["tier"] if rows else "free"

    onetime = os.environ.get("STARS_ONETIME_PRICE", "200")
    monthly = os.environ.get("STARS_MONTHLY_PRICE", "100")

    text = COMPARISON.format(onetime=onetime, monthly=monthly)

    buttons = []
    if tier == "free":
        buttons.append([{"text": f"⭐ One-time — {onetime} Stars", "callback_data": "pay:one_time"}])
        buttons.append([{"text": f"⭐ Monthly — {monthly} Stars/mo", "callback_data": "pay:monthly"}])
    elif tier == "one_time":
        buttons.append([{"text": f"⭐ Upgrade to Monthly — {monthly} Stars/mo", "callback_data": "pay:monthly"}])
    else:
        text += "\n✅ _You are on the Monthly plan._"

    tg.send_message(
        chat_id=user_id, text=text,
        reply_markup={"inline_keyboard": buttons} if buttons else None,
    )
