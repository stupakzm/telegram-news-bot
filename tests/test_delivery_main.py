"""Tests for delivery/main.py helpers touched by DEL-01 (concurrent fetch, config)."""
import os
import time
from unittest.mock import patch

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")

import delivery.main as main


def test_fetch_all_runs_feeds_concurrently():
    feeds = [f"https://f{i}.example/rss" for i in range(4)]

    def slow_fetch(url, _ts):
        time.sleep(0.1)
        return [{"url": url + "/a"}]

    with patch("delivery.main.fetch_today_articles", side_effect=slow_fetch):
        start = time.monotonic()
        out = main._fetch_all(feeds, 0)
    elapsed = time.monotonic() - start

    # 4 feeds × 0.1s sequentially = 0.4s; concurrent (4 workers) should be << that
    assert elapsed < 0.3
    assert set(out.keys()) == set(feeds)
    assert out[feeds[0]] == [{"url": feeds[0] + "/a"}]


def test_fetch_all_captures_per_feed_exceptions():
    feeds = ["https://ok.example/rss", "https://bad.example/rss"]

    def maybe_fail(url, _ts):
        if "bad" in url:
            raise ValueError("boom")
        return [{"url": url + "/a"}]

    with patch("delivery.main.fetch_today_articles", side_effect=maybe_fail):
        out = main._fetch_all(feeds, 0)

    assert out["https://ok.example/rss"] == [{"url": "https://ok.example/rss/a"}]
    assert isinstance(out["https://bad.example/rss"], ValueError)


def test_worker_config_reads_env(monkeypatch):
    monkeypatch.setenv("DELIVERY_MAX_WORKERS", "9")
    monkeypatch.setenv("DELIVERY_FEED_WORKERS", "3")
    assert main._max_user_workers() == 9
    assert main._feed_fetch_workers() == 3


def test_worker_config_falls_back_on_bad_value(monkeypatch):
    monkeypatch.setenv("DELIVERY_MAX_WORKERS", "not-a-number")
    assert main._max_user_workers() == main._MAX_USER_WORKERS
