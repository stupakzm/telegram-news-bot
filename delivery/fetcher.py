"""Fetch RSS feeds, return today's articles with full body text."""
import calendar
import html
import logging
import re
import time as _time

import feedparser
import requests

from bot.validation import validate_rss_url

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

_MAX_BODY_CHARS = 8000          # caps DB row size and AI prompt cost
# (connect, read): a feed host that answers at all is usually fast, but public
# RSS endpoints stall for seconds under load, so allow a generous read window.
_FETCH_TIMEOUT_SECONDS = (5, 20)
_USER_AGENT = "newsbot/1.0 (+https://t.me/)"

# One transient blip used to drop a feed for the whole hourly run (and, for a
# single-feed user, mean no delivery at all). Retry like db/client.py does.
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF = [1, 3]         # seconds before attempt 2, 3
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class FeedParseError(Exception):
    """A feed fetched OK over HTTP but could not be parsed into any entries.

    Raised so the caller records it in delivery_errors (feeding FEED-01's
    health view) instead of silently dropping a dead feed.
    """


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


def _get_with_retry(feed_url: str) -> requests.Response:
    """GET a feed, retrying transient transport errors and 429/5xx responses.

    Permanent failures (404, 410, bad TLS...) raise on the first attempt so a
    genuinely dead feed still surfaces in delivery_errors promptly.
    """
    last_exc: Exception | None = None
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            resp = requests.get(
                feed_url,
                timeout=_FETCH_TIMEOUT_SECONDS,
                headers={"User-Agent": _USER_AGENT},
            )
            if resp.status_code in _RETRYABLE_STATUS and attempt < len(_RETRY_BACKOFF):
                last_exc = requests.exceptions.HTTPError(
                    f"{resp.status_code} from {feed_url}", response=resp
                )
            else:
                resp.raise_for_status()
                return resp
        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
                requests.exceptions.ChunkedEncodingError) as exc:
            last_exc = exc
            if attempt >= len(_RETRY_BACKOFF):
                raise

        logger.info(
            "feed fetch attempt %d/%d failed for %s: %s",
            attempt + 1, _RETRY_ATTEMPTS, feed_url, last_exc,
        )
        _time.sleep(_RETRY_BACKOFF[attempt])

    raise last_exc


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

    resp = _get_with_retry(feed_url)

    parsed = feedparser.parse(resp.content)

    # A feed that yields zero entries *and* reports a parse error (bozo) is
    # broken (wrong URL, HTML page, malformed XML) rather than merely quiet.
    # Surface it so it lands in delivery_errors and the /admin feed-health view.
    if not parsed.entries and getattr(parsed, "bozo", 0):
        exc = getattr(parsed, "bozo_exception", None)
        raise FeedParseError(f"no entries; {type(exc).__name__ if exc else 'unparseable'}: {exc}")

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
