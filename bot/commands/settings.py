import time
from datetime import datetime, timezone as _utc

import db.client as db
import bot.telegram as tg

_TIER_LABEL = {"trial": "Trial (VIP)", "vip": "VIP", "svip": "SVIP", "expired": "Expired"}


def _tier_label(tier: str) -> str:
    return _TIER_LABEL.get(tier, tier)


def handle(message: dict) -> None:
    user_id = message["from"]["id"]
    chat_id = message["chat"]["id"]

    user_rows = db.execute(
        "SELECT tier, tier_expires_at, timezone FROM users WHERE user_id = ?",
        [user_id],
    )
    if not user_rows:
        tg.send_message(chat_id=chat_id, text="Please /start the bot first.")
        return

    tier = user_rows[0]["tier"]
    expires_at = user_rows[0]["tier_expires_at"]
    tz = user_rows[0]["timezone"] or "UTC"

    now = int(time.time())
    if tier in ("trial", "vip", "svip") and expires_at and now > expires_at:
        db.execute_many([(
            "UPDATE users SET tier = 'expired', tier_expires_at = NULL WHERE user_id = ?",
            [user_id],
        )])
        tier = "expired"
        expires_at = None

    feeds = db.execute("SELECT url FROM user_feeds WHERE user_id = ?", [user_id])
    keywords = db.execute("SELECT keyword FROM user_keywords WHERE user_id = ?", [user_id])

    if expires_at:
        exp_dt = datetime.fromtimestamp(expires_at, tz=_utc.utc).strftime("%b %d, %Y")
        plan_line = f"*Plan:* {_tier_label(tier)} (expires {exp_dt} UTC)"
    else:
        plan_line = f"*Plan:* {_tier_label(tier)}"

    text = (
        "⚙️ *Your Settings*\n\n"
        f"{plan_line}\n"
        f"*Timezone:* {tz}\n"
        f"*Feeds:* {len(feeds)}\n"
        f"*Keywords:* {len(keywords)}\n\n"
        "• /keywords — manage filter words\n"
        "• /addurl — manage RSS feeds\n"
        "• /timezone — set timezone\n"
        "• /plan — buy or switch plan\n"
    )

    result = tg.send_message(chat_id=chat_id, text=text)
    if result.get("message_id"):
        db.track_bot_message(user_id, result["message_id"])
