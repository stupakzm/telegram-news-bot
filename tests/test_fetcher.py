# tests/test_fetcher.py
import pytest
from unittest.mock import patch, MagicMock
from fetcher import fetch_articles, load_posted_ids, save_posted_ids


def make_feed(entries):
    feed = MagicMock()
    feed.entries = entries
    return feed


def make_entry(title, link, summary="A summary."):
    e = MagicMock()
    e.title = title
    e.link = link
    e.summary = summary
    return e


@patch("fetcher.feedparser.parse")
def test_fetch_articles_returns_new_only(mock_parse):
    mock_parse.return_value = make_feed([
        make_entry("Article A", "https://example.com/a"),
        make_entry("Article B", "https://example.com/b"),
    ])
    posted_ids = {"https://example.com/a"}
    results = fetch_articles(["https://example.com/feed"], "#tech", posted_ids)
    assert len(results) == 1
    assert results[0]["url"] == "https://example.com/b"


@patch("fetcher.feedparser.parse")
def test_fetch_articles_includes_category(mock_parse):
    mock_parse.return_value = make_feed([
        make_entry("Article C", "https://example.com/c"),
    ])
    results = fetch_articles(["https://example.com/feed"], "#ai", set())
    assert results[0]["category"] == "#ai"


@patch("fetcher.feedparser.parse")
def test_fetch_articles_skips_on_parse_error(mock_parse):
    mock_parse.side_effect = Exception("network error")
    results = fetch_articles(["https://example.com/bad"], "#tech", set())
    assert results == []


def test_load_posted_ids_returns_set(tmp_path):
    f = tmp_path / "posted_ids.json"
    f.write_text('["https://a.com", "https://b.com"]')
    ids = load_posted_ids(str(f))
    assert ids == {"https://a.com", "https://b.com"}


def test_load_posted_ids_missing_file(tmp_path):
    ids = load_posted_ids(str(tmp_path / "missing.json"))
    assert ids == set()


def test_save_posted_ids_caps_at_max(tmp_path):
    f = tmp_path / "posted_ids.json"
    ids = {f"https://example.com/{i}" for i in range(1500)}
    save_posted_ids(str(f), ids, max_size=1000)
    import json
    saved = json.loads(f.read_text())
    assert len(saved) == 1000
