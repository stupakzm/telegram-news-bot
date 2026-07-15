"""Tests for delivery/personalize.py — gentle per-feed reaction bias (DQ-01)."""
import os
from unittest.mock import patch

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")

from delivery import personalize as p


# --- feed_quota thresholds ---------------------------------------------------

def test_quota_default_when_neutral():
    assert p.feed_quota(0) == 2
    assert p.feed_quota(2) == 2
    assert p.feed_quota(-2) == 2


def test_quota_promotes_liked_feed():
    assert p.feed_quota(3) == 3
    assert p.feed_quota(10) == 3


def test_quota_demotes_disliked_feed_but_never_silences():
    assert p.feed_quota(-3) == 1
    assert p.feed_quota(-100) == 1  # floor at 1, never 0


# --- select_with_bias --------------------------------------------------------

def _pool(feed, n):
    return [{"feed_url": feed, "article_url": f"{feed}/{i}", "score": n - i} for i in range(n)]


def test_no_reactions_keeps_default_quota_and_order():
    feeds = ["A", "B"]
    by_feed = {"A": _pool("A", 4), "B": _pool("B", 4)}
    out = p.select_with_bias(feeds, by_feed, bias={})
    # 2 per feed, feed order A then B
    assert [a["article_url"] for a in out] == ["A/0", "A/1", "B/0", "B/1"]


def test_liked_feed_gets_more_and_sorts_first():
    feeds = ["A", "B"]
    by_feed = {"A": _pool("A", 4), "B": _pool("B", 4)}
    out = p.select_with_bias(feeds, by_feed, bias={"B": 5})  # B liked
    urls = [a["article_url"] for a in out]
    assert urls[:3] == ["B/0", "B/1", "B/2"]   # B promoted to quota 3, ordered first
    assert urls[3:] == ["A/0", "A/1"]          # A default quota 2


def test_disliked_feed_gets_fewer():
    feeds = ["A", "B"]
    by_feed = {"A": _pool("A", 4), "B": _pool("B", 4)}
    out = p.select_with_bias(feeds, by_feed, bias={"A": -5})  # A disliked
    counts = {}
    for a in out:
        counts[a["feed_url"]] = counts.get(a["feed_url"], 0) + 1
    assert counts["A"] == 1
    assert counts["B"] == 2


def test_ties_preserve_original_feed_order():
    feeds = ["A", "B", "C"]
    by_feed = {f: _pool(f, 2) for f in feeds}
    out = p.select_with_bias(feeds, by_feed, bias={})  # all neutral
    seen_feeds = [a["feed_url"] for a in out]
    assert seen_feeds == ["A", "A", "B", "B", "C", "C"]


# --- DB-backed helpers -------------------------------------------------------

@patch("delivery.personalize.db.execute")
def test_feed_reaction_bias_shapes_result(mock_execute):
    mock_execute.return_value = [
        {"feed_url": "https://a/rss", "net": 4},
        {"feed_url": "https://b/rss", "net": -2},
        {"feed_url": "https://c/rss", "net": None},
    ]
    bias = p.feed_reaction_bias(user_id=1, since_ts=0)
    assert bias == {"https://a/rss": 4, "https://b/rss": -2, "https://c/rss": 0}
    sql = mock_execute.call_args[0][0]
    assert "article_reactions" in sql and "JOIN seen_articles" in sql


@patch("delivery.personalize.db.execute")
def test_reaction_totals(mock_execute):
    mock_execute.return_value = [{"reaction": "up", "c": 7}, {"reaction": "down", "c": 2}]
    assert p.reaction_totals(0) == (7, 2)


@patch("delivery.personalize.db.execute", return_value=[])
def test_reaction_totals_empty(mock_execute):
    assert p.reaction_totals(0) == (0, 0)
