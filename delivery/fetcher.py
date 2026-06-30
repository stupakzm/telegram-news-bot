"""Fetch RSS feeds, return today's articles with full body text."""
import calendar
import html
import logging
import re

import feedparser
import requests

from bot.validation import validate_rss_url

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

_MAX_BODY_CHARS = 8000          # caps DB row size and AI prompt cost
_FETCH_TIMEOUT_SECONDS = 8
_USER_AGENT = "newsbot/1.0 (+https://t.me/)"


def _strip_html(raw: str) -> str:
    if not raw:
        return ""
    text = _HTML_TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _entry_body(entry) -> str:
    """Prefer the full <content:encoded> body when present, fall back to summary."""
    content = getattr(entry, "content", None)
    if content:
        try:
            return content[0].get("value", "") or ""
        except (IndexError, AttributeError, TypeError):
            pass
    return getattr(entry, "summary", "") or ""


def _entry_timestamp(entry) -> int | None:
    for attr in ("published_parsed", "updated_parsed"):
        struct = getattr(entry, attr, None)
        if struct:
            try:
                return calendar.timegm(struct)
            except (TypeError, ValueError):
                continue
    return None


def fetch_today_articles(feed_url: str, today_start_ts: int) -> list[dict]:
    """
    Fetch a feed and return entries dated on/after today_start_ts.

    Returns: list of {url, title, body, published_at} dicts.
    Entries without a parseable date are included (treated as fresh) so feeds
    that omit timestamps still surface in the pool.

    Raises requests.RequestException on transport errors so the caller can
    log the failure to delivery_errors and skip the URL.
    """
    if not validate_rss_url(feed_url):
        logger.warning("fetch_today_articles: blocked unsafe URL %s", feed_url)
        return []

    resp = requests.get(
        feed_url,
        timeout=_FETCH_TIMEOUT_SECONDS,
        headers={"User-Agent": _USER_AGENT},
    )
    resp.raise_for_status()

    parsed = feedparser.parse(resp.content)
    articles: list[dict] = []

    for entry in parsed.entries:
        url = getattr(entry, "link", None)
        title = getattr(entry, "title", None)
        if not url or not title:
            continue

        published_at = _entry_timestamp(entry)
        if published_at is not None and published_at < today_start_ts:
            continue

        body = _strip_html(_entry_body(entry))[:_MAX_BODY_CHARS]
        articles.append({
            "url": url,
            "title": _strip_html(title),
            "body": body,
            "published_at": published_at or 0,
        })

    return articles
