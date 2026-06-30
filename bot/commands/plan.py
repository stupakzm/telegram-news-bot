"""`/plan` — view current plan, buy / renew / switch."""
import os
import time
from datetime import datetime, timezone as _utc
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import db.client as db
import bot.telegram as tg

_TIER_LABEL = {"trial": "Trial (VIP)", "vip": "VIP", "svip": "SVIP", "expired": "Expired"}


def _user(user_id: int) -> dict | None:
    rows = db.execute(
        "SELECT tier, tier_expires_at, timezone FROM users WHERE user_id = ?",
        [user_id],
    )
    return rows[0] if rows else None


def _expiry_str(expires_at: int, tz_name: str | None) -> str:
    tz = _utc.utc
    if tz_name:
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            tz = _utc.utc
    return datetime.fromtimestamp(expires_at, tz=tz).strftime("%b %d, %Y %H:%M")


def _vip_price() -> int:
    return int(os.environ.get("STARS_VIP_PRICE", "100"))


def _svip_price() -> int:
    return int(os.environ.get("STARS_SVIP_PRICE", "290"))


def _auto_expire(user_id: int, user: dict, now: int) -> dict:
    """Downgrade in DB + in-memory if past expiry."""
    if user["tier"] in ("trial", "vip", "svip") and user["tier_expires_at"] and now > user["tier_expires_at"]:
        db.execute_many([(
            "UPDATE users SET tier = 'expired', tier_expires_at = NULL WHERE user_id = ?",
            [user_id],
        )])
        return {**user, "tier": "expired", "tier_expires_at": None}
    return user


def _build_view(user: dict) -> tuple[str, dict]:
    tier = user["tier"]
    expires_at = user["tier_expires_at"]
    tz_name = user["timezone"] or "UTC"
    vip = _vip_price()
    svip = _svip_price()

    lines = ["💎 *Plans*", ""]

    if tier == "trial":
        lines.append(f"You're on a *Trial (VIP-level)* — expires {_expiry_str(expires_at, tz_name)} {tz_name}.")
        lines.append("Pick a plan to continue past the trial:")
    elif tier == "vip":
        lines.append(f"Current: *VIP* — expires {_expiry_str(expires_at, tz_name)} {tz_name}.")
    elif tier == "svip":
        lines.append(f"Current: *SVIP* — expires {_expiry_str(expires_at, tz_name)} {tz_name}.")
    else:
        lines.append("Your plan is *expired*. Your feeds and keywords are saved.")
        lines.append("Pick a plan to resume deliveries:")

    lines.extend([
        "",
        f"*VIP — {vip}⭐ / 30 days*",
        "• 7 custom RSS feeds",
        "• 2 deliveries/day (13:00, 20:00 local)",
        "• Keyword-filtered AI summaries",
        "",
        f"*SVIP — {svip}⭐ / 30 days*",
        "• 15 custom RSS feeds",
        "• 4 deliveries/day (10:00, 14:00, 18:00, 22:00 local)",
        "• Keyword-filtered AI summaries",
        "",
        "_No autorenew. Switching restarts the 30-day clock (no rollover)._",
    ])

    buttons: list[list[dict]] = []
    if tier == "vip":
        buttons.append([{"text": f"🔁 Renew VIP — {vip}⭐", "callback_data": "pay:vip"}])
        buttons.append([{"text": f"⬆️ Switch to SVIP — {svip}⭐", "callback_data": "pay:svip"}])
    elif tier == "svip":
        buttons.append([{"text": f"🔁 Renew SVIP — {svip}⭐", "callback_data": "pay:svip"}])
        buttons.append([{"text": f"⬇️ Switch to VIP — {vip}⭐", "callback_data": "pay:vip"}])
    else:
        buttons.append([{"text": f"⭐ Activate VIP — {vip}⭐", "callback_data": "pay:vip"}])
        buttons.append([{"text": f"⭐ Activate SVIP — {svip}⭐", "callback_data": "pay:svip"}])

    return "\n".join(lines), {"inline_keyboard": buttons}


def handle(message: dict) -> None:
    user_id = message["from"]["id"]
    chat_id = message["chat"]["id"]

    user = _user(user_id)
    if not user:
        tg.send_message(chat_id=chat_id, text="Please /start the bot first.")
        return

    user = _auto_expire(user_id, user, int(time.time()))
    text, markup = _build_view(user)
    result = tg.send_message(chat_id=chat_id, text=text, reply_markup=markup)
    if result.get("message_id"):
        db.track_bot_message(user_id, result["message_id"])
