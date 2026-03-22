import os
import time
import logging
logger = logging.getLogger(__name__)
import requests
import db.client as db

FREE_ARTICLES_PER_THEME = 1
EXPIRY_REMINDER_WINDOW = 3 * 24 * 3600   # 3 days in seconds
REMINDER_COOLDOWN = 24 * 3600             # re-remind after 24h


def get_due_deliveries(hour_utc: int, weekday: int) -> list[dict]:
    """
    Query users scheduled for delivery at this hour on this weekday.
    weekday: 1=Mon, 2=Tue, ..., 7=Sun (ISO weekday).
    Returns list of delivery dicts with effective_articles_per_theme applied.
    """
    rows = db.execute(
        """
        SELECT
            u.user_id, u.tier, u.tier_expires_at, u.last_reminder_at,
            ut.theme_type, ut.theme_id, ut.articles_per_theme
        FROM user_schedules us
        JOIN users u ON u.user_id = us.user_id
        LEFT JOIN user_themes ut ON ut.id = us.user_theme_id
        WHERE us.hour_utc = ?
          AND EXISTS (
            SELECT 1 FROM json_each(us.days) WHERE CAST(value AS INTEGER) = ?
          )
        """,
        [hour_utc, weekday],
    )
    now = int(time.time())
    result = []
    for row in rows:
        effective_tier = row["tier"]
        if row["tier"] == "monthly" and row["tier_expires_at"] and row["tier_expires_at"] < now:
            effective_tier = "free"
            # Downgrade in DB
            db.execute(
                "UPDATE users SET tier = 'free', tier_expires_at = NULL WHERE user_id = ?",
                [row["user_id"]],
            )

        max_articles = FREE_ARTICLES_PER_THEME if effective_tier == "free" else row["articles_per_theme"]
        result.append({**row, "effective_articles_per_theme": max_articles, "effective_tier": effective_tier})

    return result


def group_by_theme(deliveries: list[dict]) -> dict:
    """Group delivery rows by (theme_type, theme_id)."""
    groups: dict[tuple, list[dict]] = {}
    for d in deliveries:
        key = (d["theme_type"], d["theme_id"])
        groups.setdefault(key, []).append(d)
    return groups


def check_expiry_reminders() -> None:
    """
    Send renewal reminders to monthly users expiring within 3 days.
    Runs once per hourly cron. Uses last_reminder_at to avoid duplicate sends.
    """
    now = int(time.time())
    window_end = now + EXPIRY_REMINDER_WINDOW

    users = db.execute(
        """
        SELECT user_id, tier_expires_at, last_reminder_at
        FROM users
        WHERE tier = 'monthly'
          AND tier_expires_at IS NOT NULL
          AND tier_expires_at BETWEEN ? AND ?
          AND (last_reminder_at IS NULL OR last_reminder_at < ?)
        """,
        [now, window_end, now - REMINDER_COOLDOWN],
    )

    if not users:
        return

    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    for user in users:
        days_left = max(1, (user["tier_expires_at"] - now + 86399) // 86400)
        text = (
            f"⏳ Your monthly subscription expires in {days_left} day(s). "
            f"Use /upgrade to renew and keep your personalized feed."
        )
        try:
            requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": user["user_id"], "text": text},
                timeout=10,
            )
        except Exception as e:
            logger.warning("Failed to send expiry reminder to user %s: %s", user["user_id"], e)
            continue  # don't update DB if send failed
        try:
            db.execute_many([
                ("UPDATE users SET last_reminder_at = ? WHERE user_id = ?",
                 [now, user["user_id"]])
            ])
        except Exception as e:
            logger.warning("Failed to update last_reminder_at for user %s: %s", user["user_id"], e)
