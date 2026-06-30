import json
import time
from datetime import datetime, timezone

import db.client as db
import bot.telegram as tg

TRIAL_DURATION_SECONDS = 3 * 24 * 3600

WELCOME_NEW = """\
👋 *Welcome to NewsBot!*

I deliver AI-curated news that matches *your keywords* — from RSS feeds *you choose*.

You're on a *3-day VIP trial*:
• Up to 7 custom feeds
• 2 deliveries per day
• Filtered by your keywords

Pick a starter pack to import 2–3 RSS feeds, or skip and use /addurl.
"""

WELCOME_RETURNING = """\
👋 *Welcome back!*

Your plan: *{tier_label}*{expires_line}

• /keywords — your filter words
• /addurl — add RSS feeds
• /timezone — set local timezone
• /settings — overview
• /plan — buy or switch plan
"""

WELCOME_EXPIRED = """\
👋 *Welcome back!*

Your plan has expired. Your feeds and keywords are still saved.

Use /plan to renew and resume deliveries.
"""


def _tier_label(tier: str) -> str:
    return {"trial": "Trial (VIP)", "vip": "VIP", "svip": "SVIP", "expired": "Expired"}.get(tier, tier)


def _start_trial(user_id: int, now: int) -> None:
    db.execute_many([(
        "INSERT INTO users (user_id, tier, tier_expires_at, trial_used, stars_paid, created_at) "
        "VALUES (?, 'trial', ?, 1, 0, ?)",
        [user_id, now + TRIAL_DURATION_SECONDS, now],
    )])


def _pack_keyboard() -> dict:
    rows = db.execute(
        "SELECT id, name FROM url_packs WHERE is_active = 1 ORDER BY id"
    )
    buttons = [
        [{"text": f"\U0001f4e6 {p['name']}", "callback_data": f"start:pack:{p['id']}"}]
        for p in rows
    ]
    buttons.append([{"text": "Skip — I'll add my own", "callback_data": "start:skip"}])
    return {"inline_keyboard": buttons}


def _import_pack(user_id: int, pack_id: int) -> int:
    """Import URLs from a pack into user_feeds. Returns count actually inserted."""
    rows = db.execute("SELECT urls FROM url_packs WHERE id = ?", [pack_id])
    if not rows:
        return 0
    urls = json.loads(rows[0]["urls"])
    now = int(time.time())
    statements = [
        (
            "INSERT OR IGNORE INTO user_feeds (user_id, url, added_at) VALUES (?, ?, ?)",
            [user_id, url, now],
        )
        for url in urls
    ]
    db.execute_many(statements)
    return len(urls)


def handle(message: dict) -> None:
    user_id = message["from"]["id"]
    chat_id = message["chat"]["id"]
    now = int(time.time())

    rows = db.execute(
        "SELECT tier, tier_expires_at FROM users WHERE user_id = ?",
        [user_id],
    )

    if not rows:
        _start_trial(user_id, now)
        result = tg.send_message(chat_id=chat_id, text=WELCOME_NEW, reply_markup=_pack_keyboard())
        if result.get("message_id"):
            db.track_bot_message(user_id, result["message_id"])
        return

    tier = rows[0]["tier"]
    expires_at = rows[0]["tier_expires_at"]

    if tier in ("trial", "vip", "svip") and expires_at and now > expires_at:
        db.execute_many([(
            "UPDATE users SET tier = 'expired', tier_expires_at = NULL WHERE user_id = ?",
            [user_id],
        )])
        tier = "expired"
        expires_at = None

    if tier == "expired":
        result = tg.send_message(chat_id=chat_id, text=WELCOME_EXPIRED)
        if result.get("message_id"):
            db.track_bot_message(user_id, result["message_id"])
        return

    if expires_at:
        exp_str = datetime.fromtimestamp(expires_at, tz=timezone.utc).strftime("%b %d, %Y")
        expires_line = f" (expires {exp_str} UTC)"
    else:
        expires_line = ""

    text = WELCOME_RETURNING.format(tier_label=_tier_label(tier), expires_line=expires_line)
    result = tg.send_message(chat_id=chat_id, text=text)
    if result.get("message_id"):
        db.track_bot_message(user_id, result["message_id"])


def handle_pack_callback(callback_query: dict, pack_id: int) -> None:
    user_id = callback_query["from"]["id"]
    msg = callback_query.get("message", {})
    chat_id = msg.get("chat", {}).get("id", user_id)

    rows = db.execute("SELECT name FROM url_packs WHERE id = ?", [pack_id])
    if not rows:
        tg.answer_callback_query(callback_query["id"], text="Pack not found.")
        return

    count = _import_pack(user_id, pack_id)
    pack_name = rows[0]["name"]

    text = (
        f"✅ Imported *{count}* feed(s) from *{pack_name}*.\n\n"
        "Next steps:\n"
        "• /keywords — add filter words (deliveries need at least one)\n"
        "• /timezone — set your local timezone\n"
        "• /addurl — add more RSS feeds\n"
        "• /settings — see everything\n"
    )
    tg.answer_callback_query(callback_query["id"], text=f"Imported {count} feed(s).")
    result = tg.send_message(chat_id=chat_id, text=text)
    if result.get("message_id"):
        db.track_bot_message(user_id, result["message_id"])


def handle_skip_callback(callback_query: dict) -> None:
    user_id = callback_query["from"]["id"]
    msg = callback_query.get("message", {})
    chat_id = msg.get("chat", {}).get("id", user_id)

    text = (
        "OK — starting from scratch.\n\n"
        "• /addurl — add an RSS feed URL\n"
        "• /keywords — add filter words (required for deliveries)\n"
        "• /timezone — set your local timezone\n"
    )
    tg.answer_callback_query(callback_query["id"])
    result = tg.send_message(chat_id=chat_id, text=text)
    if result.get("message_id"):
        db.track_bot_message(user_id, result["message_id"])
