import pytest
from unittest.mock import patch, MagicMock
import os

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")


def _make_entry(url, title, summary):
    e = MagicMock()
    e.link = url
    e.title = title
    e.summary = summary
    return e


def _theme(hashtag="#ai", feeds=None):
    return {
        "id": 1,
        "theme_type": "default",
        "name": "AI",
        "hashtag": hashtag,
        "rss_feeds": feeds or ["https://feed.example.com/rss"],
    }


@patch("delivery.fetcher.feedparser.parse")
@patch("delivery.fetcher.db.execute")
def test_fetch_articles_filters_posted(mock_execute, mock_parse):
    mock_execute.return_value = [{"url": "https://old.com/1"}]
    mock_parse.return_value = MagicMock(entries=[
        _make_entry("https://old.com/1", "Old", "Already posted"),
        _make_entry("https://new.com/2", "New", "Fresh article"),
    ])

    from delivery.fetcher import fetch_articles
    result = fetch_articles(_theme())

    assert len(result) == 1
    assert result[0]["url"] == "https://new.com/2"
    assert result[0]["title"] == "New"


@patch("delivery.fetcher.feedparser.parse")
@patch("delivery.fetcher.db.execute")
def test_fetch_articles_returns_correct_shape(mock_execute, mock_parse):
    mock_execute.return_value = []
    mock_parse.return_value = MagicMock(entries=[
        _make_entry("https://new.com/1", "Title", "Summary text"),
    ])

    from delivery.fetcher import fetch_articles
    result = fetch_articles(_theme(hashtag="#ai"))

    assert result[0] == {
        "url": "https://new.com/1",
        "title": "Title",
        "description": "Summary text",
        "theme_type": "default",
        "theme_id": 1,
        "hashtag": "#ai",
    }


@patch("delivery.fetcher.feedparser.parse", side_effect=Exception("network error"))
@patch("delivery.fetcher.db.execute")
def test_fetch_articles_skips_broken_feed(mock_execute, mock_parse):
    mock_execute.return_value = []

    from delivery.fetcher import fetch_articles
    result = fetch_articles(_theme())
    assert result == []
