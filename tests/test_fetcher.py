import os
import time
from unittest.mock import patch, MagicMock

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")


def _fake_entry(link, title, content=None, summary="", published=None):
    entry = MagicMock()
    entry.link = link
    entry.title = title
    if content is not None:
        entry.content = [{"value": content}]
    else:
        # MagicMock auto-creates attrs; suppress 'content'
        entry.content = None
    entry.summary = summary
    entry.published_parsed = published
    entry.updated_parsed = None
    return entry


def _fake_resp(content=b"<rss/>"):
    resp = MagicMock()
    resp.content = content
    resp.raise_for_status = MagicMock()
    return resp


@patch("delivery.fetcher.feedparser.parse")
@patch("delivery.fetcher.requests.get")
@patch("delivery.fetcher.validate_rss_url", return_value=True)
def test_skips_articles_older_than_today(mock_validate, mock_get, mock_parse):
    mock_get.return_value = _fake_resp()
    parsed = MagicMock()
    today_ts = int(time.time())
    parsed.entries = [
        _fake_entry(
            "https://example.com/a",
            "old article",
            summary="content",
            published=time.gmtime(today_ts - 2 * 86400),
        ),
        _fake_entry(
            "https://example.com/b",
            "new article",
            summary="content",
            published=time.gmtime(today_ts),
        ),
    ]
    mock_parse.return_value = parsed

    from delivery.fetcher import fetch_today_articles
    out = fetch_today_articles("https://feed.example/rss", today_ts - 3600)
    urls = [a["url"] for a in out]
    assert "https://example.com/b" in urls
    assert "https://example.com/a" not in urls


@patch("delivery.fetcher.feedparser.parse")
@patch("delivery.fetcher.requests.get")
@patch("delivery.fetcher.validate_rss_url", return_value=True)
def test_prefers_content_over_summary(mock_validate, mock_get, mock_parse):
    mock_get.return_value = _fake_resp()
    parsed = MagicMock()
    parsed.entries = [
        _fake_entry(
            "https://example.com/c",
            "title",
            content="<p>Full body</p>",
            summary="Short summary",
            published=time.gmtime(int(time.time())),
        ),
    ]
    mock_parse.return_value = parsed

    from delivery.fetcher import fetch_today_articles
    out = fetch_today_articles("https://feed.example/rss", 0)
    assert out[0]["body"] == "Full body"


@patch("delivery.fetcher.feedparser.parse")
@patch("delivery.fetcher.requests.get")
@patch("delivery.fetcher.validate_rss_url", return_value=True)
def test_falls_back_to_summary_when_no_content(mock_validate, mock_get, mock_parse):
    mock_get.return_value = _fake_resp()
    parsed = MagicMock()
    parsed.entries = [
        _fake_entry(
            "https://example.com/d",
            "title",
            content=None,
            summary="<p>Summary <b>html</b></p>",
            published=time.gmtime(int(time.time())),
        ),
    ]
    mock_parse.return_value = parsed

    from delivery.fetcher import fetch_today_articles
    out = fetch_today_articles("https://feed.example/rss", 0)
    assert out[0]["body"] == "Summary html"


@patch("delivery.fetcher.feedparser.parse")
@patch("delivery.fetcher.requests.get")
@patch("delivery.fetcher.validate_rss_url", return_value=True)
def test_undated_entry_is_included(mock_validate, mock_get, mock_parse):
    mock_get.return_value = _fake_resp()
    parsed = MagicMock()
    parsed.entries = [
        _fake_entry("https://example.com/e", "title", summary="text", published=None),
    ]
    mock_parse.return_value = parsed

    from delivery.fetcher import fetch_today_articles
    out = fetch_today_articles("https://feed.example/rss", int(time.time()))
    assert len(out) == 1
    assert out[0]["published_at"] == 0


@patch("delivery.fetcher.feedparser.parse")
@patch("delivery.fetcher.requests.get")
@patch("delivery.fetcher.validate_rss_url", return_value=True)
def test_caps_body_at_8000_chars(mock_validate, mock_get, mock_parse):
    mock_get.return_value = _fake_resp()
    long_body = "A" * 20000
    parsed = MagicMock()
    parsed.entries = [
        _fake_entry(
            "https://example.com/f",
            "title",
            content=long_body,
            published=time.gmtime(int(time.time())),
        ),
    ]
    mock_parse.return_value = parsed

    from delivery.fetcher import fetch_today_articles
    out = fetch_today_articles("https://feed.example/rss", 0)
    assert len(out[0]["body"]) == 8000


@patch("delivery.fetcher.validate_rss_url", return_value=False)
def test_unsafe_url_returns_empty(mock_validate):
    from delivery.fetcher import fetch_today_articles
    out = fetch_today_articles("http://10.0.0.1/feed", 0)
    assert out == []


@patch("delivery.fetcher.feedparser.parse")
@patch("delivery.fetcher.requests.get")
@patch("delivery.fetcher.validate_rss_url", return_value=True)
def test_strips_html_entities(mock_validate, mock_get, mock_parse):
    mock_get.return_value = _fake_resp()
    parsed = MagicMock()
    parsed.entries = [
        _fake_entry(
            "https://example.com/g",
            "M&amp;S launch",
            content="Apple &amp; Google partner",
            published=time.gmtime(int(time.time())),
        ),
    ]
    mock_parse.return_value = parsed

    from delivery.fetcher import fetch_today_articles
    out = fetch_today_articles("https://feed.example/rss", 0)
    assert out[0]["title"] == "M&S launch"
    assert out[0]["body"] == "Apple & Google partner"
