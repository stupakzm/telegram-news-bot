"""Feed-health signal (FEED-01).

Aggregates per-feed failures already recorded in `delivery_errors` (transport
errors and unparseable/empty feeds raised by delivery/fetcher.py) so the
`/admin` dashboard can show which feeds are consistently broken, instead of the
raw-errors list alone. No schema change — reads existing data.
"""
import time

import db.client as db

DEFAULT_WINDOW_SECONDS = 7 * 24 * 3600
DEFAULT_LIMIT = 5


def feed_health_report(
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
    limit: int = DEFAULT_LIMIT,
    now_ts: int | None = None,
) -> list[dict]:
    """Return the feeds with the most recorded failures in the recent window.

    Each row: {feed_url, failures, last_at, affected_users}. Ordered by failure
    count desc, then most-recent failure. Feeds with a NULL feed_url (global
    errors) are excluded.
    """
    now_ts = int(time.time()) if now_ts is None else now_ts
    since = now_ts - window_seconds
    return db.execute(
        "SELECT feed_url, "
        "       COUNT(*) AS failures, "
        "       MAX(occurred_at) AS last_at, "
        "       COUNT(DISTINCT user_id) AS affected_users "
        "FROM delivery_errors "
        "WHERE feed_url IS NOT NULL AND occurred_at >= ? "
        "GROUP BY feed_url "
        "ORDER BY failures DESC, last_at DESC "
        "LIMIT ?",
        [since, limit],
    )


def _shorten(url: str, width: int = 48) -> str:
    return url if len(url) <= width else url[: width - 1] + "…"


def format_feed_health(rows: list[dict], now_ts: int | None = None) -> list[str]:
    """Render report rows as Telegram-markdown bullet lines (list of strings)."""
    if not rows:
        return ["None \U0001f7e2"]  # green — no failing feeds
    now_ts = int(time.time()) if now_ts is None else now_ts
    lines = []
    for r in rows:
        age_h = max(0, (now_ts - (r["last_at"] or now_ts)) // 3600)
        users = r.get("affected_users") or 0
        user_note = f", {users} user(s)" if users else ""
        lines.append(
            f"• {r['failures']}× `{_shorten(r['feed_url'])}` "
            f"(last {age_h}h ago{user_note})"
        )
    return lines
