"""Reaction-driven personalization (DQ-01).

Gentle per-feed bias: a user's recent 👍/👎 on delivered articles nudge how many
articles each feed contributes to the next digest. Keyword scoring stays the
primary signal — reactions only adjust the per-feed pick quota within tight
bounds and order liked feeds first. Fully reversible: with no reactions, every
feed keeps its default quota and original order.
"""
import db.client as db

REACTION_WINDOW_SECONDS = 30 * 24 * 3600

_BASE_QUOTA = 2          # default articles per feed per run
_DISLIKE_THRESHOLD = -3  # net reactions at/below this demote a feed
_LIKE_THRESHOLD = 3      # net reactions at/above this promote a feed


def feed_reaction_bias(user_id: int, since_ts: int) -> dict[str, int]:
    """Net reaction (up +1 / down -1) per feed for a user over a recent window.

    Joins article_reactions to seen_articles to attribute each reaction to the
    feed the article came from. Returns {feed_url: net_score}.
    """
    rows = db.execute(
        "SELECT sa.feed_url AS feed_url, "
        "       SUM(CASE ar.reaction WHEN 'up' THEN 1 WHEN 'down' THEN -1 ELSE 0 END) AS net "
        "FROM article_reactions ar "
        "JOIN seen_articles sa "
        "  ON sa.user_id = ar.user_id AND sa.article_url = ar.article_url "
        "WHERE ar.user_id = ? AND ar.reacted_at >= ? "
        "GROUP BY sa.feed_url",
        [user_id, since_ts],
    )
    return {r["feed_url"]: int(r["net"] or 0) for r in rows}


def feed_quota(net: int, base: int = _BASE_QUOTA) -> int:
    """How many articles a feed may contribute, adjusted by its net reaction."""
    if net <= _DISLIKE_THRESHOLD:
        return max(1, base - 1)   # demote, but never silence a feed entirely
    if net >= _LIKE_THRESHOLD:
        return base + 1           # promote a consistently-liked feed
    return base


def select_with_bias(
    feeds: list[str],
    by_feed: dict[str, list],
    bias: dict[str, int],
    base: int = _BASE_QUOTA,
) -> list:
    """Pick each feed's top articles with a reaction-adjusted quota.

    `by_feed[feed]` must already be ordered best-first (score desc). Feeds are
    ordered liked-first for send order; ties keep the user's original feed
    order (stable sort). Inclusion is governed by each feed's quota.
    """
    ordered_feeds = sorted(feeds, key=lambda f: -bias.get(f, 0))
    selected: list = []
    for feed_url in ordered_feeds:
        quota = feed_quota(bias.get(feed_url, 0), base)
        selected.extend(by_feed.get(feed_url, [])[:quota])
    return selected


def reaction_totals(since_ts: int) -> tuple[int, int]:
    """Global (up, down) reaction counts since a timestamp — for /admin."""
    rows = db.execute(
        "SELECT reaction, COUNT(*) AS c FROM article_reactions "
        "WHERE reacted_at >= ? GROUP BY reaction",
        [since_ts],
    )
    counts = {r["reaction"]: int(r["c"]) for r in rows}
    return counts.get("up", 0), counts.get("down", 0)
