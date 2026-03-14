import json
import time
import db.client as db


def current_quarter(hour: int) -> int:
    """Map UTC hour (0-23) to quarter index (0-3)."""
    return hour // 6


def get_cached(theme_type: str, theme_id: int, date: str, quarter: int) -> list[dict] | None:
    """Return cached article list, or None on cache miss."""
    rows = db.execute(
        "SELECT articles FROM theme_cache "
        "WHERE theme_type = ? AND theme_id = ? AND cache_date = ? AND quarter = ?",
        [theme_type, theme_id, date, quarter],
    )
    if not rows:
        return None
    return json.loads(rows[0]["articles"])


def set_cache(theme_type: str, theme_id: int, date: str, quarter: int, articles: list[dict]) -> None:
    """Write or replace a cache entry for this theme + quarter."""
    db.execute_many([
        (
            "INSERT OR REPLACE INTO theme_cache "
            "(theme_type, theme_id, cache_date, quarter, articles, generated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [theme_type, theme_id, date, quarter, json.dumps(articles), int(time.time())],
        )
    ])
