"""Pick which users are due for delivery on the current hourly cron tick."""
import logging
import os
import time
from datetime import datetime, timedelta, timezone as _utc
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

# Slot catch-up. A run covers every hourly slot since the last successful run,
# so a tick that GitHub drops (no hosted runner acquired) or fires late doesn't
# silently cost a user their digest. Capped so that a long outage backfills the
# recent slots rather than replaying a whole day of them.
MAX_CATCHUP_HOURS = 6

_RUN_STATE_DDL = (
    "CREATE TABLE IF NOT EXISTS run_state ("
    "key TEXT PRIMARY KEY, "
    "value INTEGER NOT NULL, "
    "updated_at INTEGER NOT NULL)"
)
_LAST_RUN_KEY = "last_successful_run"

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


def _floor_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def get_last_successful_run() -> int | None:
    """Unix ts of the slot covered by the last completed run, or None if unknown.

    The table is created on read so this needs no separate migration step —
    init_db.py is destructive and must not be run against live data.
    """
    try:
        db.execute_many([(_RUN_STATE_DDL, [])])
        rows = db.execute(
            "SELECT value FROM run_state WHERE key = ?", [_LAST_RUN_KEY]
        )
        return rows[0]["value"] if rows else None
    except Exception as e:
        # Falling back to None means "cover only the current slot" — the old
        # behavior, and the safe direction to fail in.
        logger.warning("run_state read failed, skipping catch-up: %s", e)
        return None


def record_successful_run(now_utc: datetime) -> None:
    """Mark this run's slot as covered so the next run doesn't repeat it."""
    try:
        db.execute_many([
            (_RUN_STATE_DDL, []),
            (
                "INSERT INTO run_state (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "updated_at = excluded.updated_at",
                [
                    _LAST_RUN_KEY,
                    int(_floor_hour(now_utc).timestamp()),
                    int(now_utc.timestamp()),
                ],
            ),
        ])
    except Exception as e:
        logger.warning("run_state write failed: %s", e)


def covered_slots(now_utc: datetime, last_run_ts: int | None) -> list[datetime]:
    """
    The hourly slot instants this run is responsible for: every slot after the
    last successful run, up to and including this one, oldest first.

    Flooring to the hour absorbs GitHub's cron drift — a tick that fires at
    17:56 covers the 17:00 slot rather than being read as a 17:00-hour run that
    was really meant for 18:00. An empty list means this slot is already covered
    by an earlier run, which is how a duplicate trigger gets deduplicated.
    """
    current = _floor_hour(now_utc)
    if last_run_ts is None:
        return [current]
    last = _floor_hour(datetime.fromtimestamp(last_run_ts, tz=_utc.utc))
    if last >= current:
        return []
    gap = int((current - last).total_seconds() // 3600)
    span = min(gap, MAX_CATCHUP_HOURS)
    return [current - timedelta(hours=i) for i in range(span - 1, -1, -1)]


def get_due_users(now_utc: datetime, slots: list[datetime] | None = None) -> list[dict]:
    """
    Return active users whose local hour, at any slot this run covers, matches
    one of their tier's scheduled delivery hours. Auto-expires any user whose
    tier_expires_at passed.

    A user due at several covered slots is still returned once: a backfilled run
    delivers their digest late, it does not send one digest per missed slot.
    """
    if slots is None:
        slots = covered_slots(now_utc, get_last_successful_run())
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
        if any(_user_local_hour(row["timezone"], slot) in hours for slot in slots):
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
