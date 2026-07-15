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

# Expiry-reminder settings. Paid plans get a 3-day heads-up to renew; trial
# users get a single final-day nudge to pick a plan.
EXPIRY_REMINDER_WINDOW = 3 * 24 * 3600
TRIAL_REMINDER_WINDOW = 24 * 3600
REMINDER_COOLDOWN = 24 * 3600


def _owner_id() -> int | None:
    """The owner's user_id, if configured — exempt from auto-expiry."""
    raw = os.environ.get("OWNER_USER_ID")
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


def _notify_expiration(user_id: int, tier: str) -> None:
    """Tell a user their plan just expired and deliveries have stopped."""
    if tier == "trial":
        text = (
            "⌛ Your 3-day trial has ended, so daily digests have stopped.\n"
            "Use /plan to pick a plan and resume deliveries."
        )
    else:
        text = (
            "⌛ Your plan has expired, so daily digests have stopped.\n"
            "Use /plan to renew and resume deliveries."
        )
    try:
        requests.post(
            f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",
            json={"chat_id": user_id, "text": text},
            timeout=10,
        )
    except Exception as e:
        logger.warning("Failed to send expiration notice to %s: %s", user_id, e)


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
    owner_id = _owner_id()
    due: list[dict] = []
    expired: list[tuple[int, str]] = []  # (user_id, tier) for users just expired

    for row in rows:
        if (
            row["tier_expires_at"]
            and row["tier_expires_at"] < now_ts
            and row["user_id"] != owner_id
        ):
            expired.append((row["user_id"], row["tier"]))
            continue

        hours = TIER_HOURS.get(row["tier"], ())
        local_hour = _user_local_hour(row["timezone"], now_utc)
        if local_hour in hours:
            due.append(row)

    if expired:
        db.execute_many([
            (
                "UPDATE users SET tier = 'expired', tier_expires_at = NULL WHERE user_id = ?",
                [uid],
            )
            for uid, _ in expired
        ])
        for uid, tier in expired:
            _notify_expiration(uid, tier)

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
            SELECT user_id, tier, tier_expires_at, last_reminder_at
            FROM users
            WHERE tier IN ('trial', 'vip', 'svip')
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
        seconds_left = user["tier_expires_at"] - now
        # Trial spans only 3 days, so warn just once in its final day rather
        # than nagging from day one.
        if user["tier"] == "trial" and seconds_left > TRIAL_REMINDER_WINDOW:
            continue
        days_left = max(1, (user["tier_expires_at"] - now + 86399) // 86400)
        if user["tier"] == "trial":
            text = (
                f"⏳ Your trial ends in {days_left} day(s). "
                "Use /plan to pick a plan and keep deliveries running."
            )
        else:
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
