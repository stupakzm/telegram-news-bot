"""Pick which users are due for delivery on the current hourly cron tick."""
import logging
import os
import time
from datetime import datetime, timezone as _utc
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

import db.client as db

logger = logging.getLogger(__name__)

# Fixed local-time delivery hours per tier. Trial maps to VIP.
TIER_HOURS = {
    "trial": (13, 20),
    "vip":   (13, 20),
    "svip":  (10, 14, 18, 22),
}

# Pool retention window — seen_articles older than this get pruned each run.
SEEN_RETENTION_SECONDS = 24 * 3600

# Renewal-reminder settings (paid plans only; trial users don't get nags).
EXPIRY_REMINDER_WINDOW = 3 * 24 * 3600
REMINDER_COOLDOWN = 24 * 3600


def _user_local_hour(user_tz: str | None, now_utc: datetime) -> int:
    if not user_tz:
        return now_utc.hour
    try:
        tz = ZoneInfo(user_tz)
    except ZoneInfoNotFoundError:
        logger.warning("Unknown timezone %r — defaulting to UTC", user_tz)
        return now_utc.hour
    return now_utc.astimezone(tz).hour


def get_due_users(now_utc: datetime) -> list[dict]:
    """
    Return active users whose current local hour matches one of their tier's
    scheduled delivery hours. Auto-expires any user whose tier_expires_at passed.
    """
    rows = db.execute(
        "SELECT user_id, tier, tier_expires_at, timezone "
        "FROM users WHERE tier IN ('trial', 'vip', 'svip')"
    )
    now_ts = int(now_utc.timestamp())
    due: list[dict] = []
    expired_ids: list[int] = []

    for row in rows:
        if row["tier_expires_at"] and row["tier_expires_at"] < now_ts:
            expired_ids.append(row["user_id"])
            continue

        hours = TIER_HOURS.get(row["tier"], ())
        local_hour = _user_local_hour(row["timezone"], now_utc)
        if local_hour in hours:
            due.append(row)

    if expired_ids:
        db.execute_many([
            (
                "UPDATE users SET tier = 'expired', tier_expires_at = NULL WHERE user_id = ?",
                [uid],
            )
            for uid in expired_ids
        ])

    return due


def cleanup_seen_articles() -> None:
    """Drop seen_articles older than the retention window so the pool stays bounded."""
    cutoff = int(time.time()) - SEEN_RETENTION_SECONDS
    try:
        db.execute_many([(
            "DELETE FROM seen_articles WHERE fetched_at < ?",
            [cutoff],
        )])
    except Exception as e:
        logger.warning("cleanup_seen_articles failed: %s", e)


def check_expiry_reminders() -> None:
    """Nudge VIP/SVIP users whose plan expires within 3 days. Once per cooldown."""
    now = int(time.time())
    window_end = now + EXPIRY_REMINDER_WINDOW
    try:
        users = db.execute(
            """
            SELECT user_id, tier_expires_at, last_reminder_at
            FROM users
            WHERE tier IN ('vip', 'svip')
              AND tier_expires_at IS NOT NULL
              AND tier_expires_at BETWEEN ? AND ?
              AND (last_reminder_at IS NULL OR last_reminder_at < ?)
            """,
            [now, window_end, now - REMINDER_COOLDOWN],
        )
    except Exception as e:
        logger.warning("check_expiry_reminders query failed: %s", e)
        return
    if not users:
        return

    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    for user in users:
        days_left = max(1, (user["tier_expires_at"] - now + 86399) // 86400)
        text = (
            f"⏳ Your plan expires in {days_left} day(s). "
            "Use /plan to renew and keep deliveries running."
        )
        try:
            requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": user["user_id"], "text": text},
                timeout=10,
            )
        except Exception as e:
            logger.warning("Failed to send expiry reminder to %s: %s", user["user_id"], e)
            continue
        try:
            db.execute_many([(
                "UPDATE users SET last_reminder_at = ? WHERE user_id = ?",
                [now, user["user_id"]],
            )])
        except Exception as e:
            logger.warning("Failed to update last_reminder_at for %s: %s", user["user_id"], e)


def user_today_start_utc_ts(user_tz: str | None, now_utc: datetime) -> int:
    """Return the Unix timestamp of midnight in the user's local timezone."""
    tz = _utc.utc
    if user_tz:
        try:
            tz = ZoneInfo(user_tz)
        except ZoneInfoNotFoundError:
            tz = _utc.utc
    local = now_utc.astimezone(tz)
    midnight_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(midnight_local.timestamp())
