"""Best-effort full-text extraction for feeds that ship stub bodies.

Some feeds carry no article text at all — Hacker News entries have a body of
literally "Comments" — so keyword scoring for them degenerates to title-only
matching and relevant posts score zero. For those feeds we follow the entry's
link and pull the prose out of the page.

Deliberately dependency-free: no trafilatura, no BeautifulSoup. A paragraph
scrape is cruder than a real extractor but adds no install weight, and the
whole path is best-effort — every failure falls back to the feed's own body,
so the worst case is exactly the previous behaviour.

Not attempted: JS-rendered pages (we see the empty shell), paywalls, and
anything behind a bot wall. Those simply return None.
"""
import logging
import re

import requests

from bot.validation import validate_rss_url
from delivery.ratelimit import TokenBucket

logger = logging.getLogger(__name__)

# HN links point at arbitrary third-party domains, so be a polite client: cap
# how fast we hit them and give up quickly on anything slow.
_LIMITER = TokenBucket(rate_per_sec=2, burst=4)
_TIMEOUT = (5, 10)
_USER_AGENT = "newsbot/1.0 (+https://t.me/)"

# Only follow links from feeds we know ship stubs. Kept explicit rather than
# triggering on short bodies, so a feed that is merely terse today can't
# silently turn into a fan-out of third-party fetches.
_STUB_FEED_HOSTS = frozenset({"news.ycombinator.com"})

_MAX_HTML_BYTES = 2_000_000     # skip video pages, huge SPAs, and the like
_MIN_USEFUL_CHARS = 200         # below this the scrape found nav junk, not prose

_DROP_BLOCKS_RE = re.compile(
    r"<(script|style|nav|header|footer|aside|form|noscript)\b.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_PARAGRAPH_RE = re.compile(r"<p\b[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def feed_ships_stubs(feed_url: str) -> bool:
    """True if this feed is known to carry no article text."""
    try:
        host = requests.utils.urlparse(feed_url).hostname or ""
    except Exception:
        return False
    return host.lower().lstrip("www.") in _STUB_FEED_HOSTS or host.lower() in _STUB_FEED_HOSTS


def fetch_article_text(url: str, max_chars: int) -> str | None:
    """Fetch an article page and return its prose, or None on any failure.

    Never raises: a miss here must not cost the user their digest.
    """
    # HN links to arbitrary domains, so this is a genuine SSRF surface.
    if not validate_rss_url(url):
        logger.info("extract: blocked unsafe URL %s", url)
        return None

    try:
        _LIMITER.acquire()
        resp = requests.get(
            url,
            timeout=_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
            stream=True,
        )
        resp.raise_for_status()

        ctype = resp.headers.get("Content-Type", "")
        if "html" not in ctype.lower():
            return None

        raw = resp.raw.read(_MAX_HTML_BYTES, decode_content=True)
        html_text = raw.decode(resp.encoding or "utf-8", errors="replace")
    except Exception as e:
        logger.info("extract: fetch failed for %s: %s", url, e)
        return None
    finally:
        try:
            resp.close()
        except Exception:
            pass

    text = _prose(html_text)
    if len(text) < _MIN_USEFUL_CHARS:
        return None
    return text[:max_chars]


def _prose(html_text: str) -> str:
    """Pull paragraph text out of a page.

    Paragraphs only — there is deliberately NO whole-page fallback. Stripping
    every tag off a page that has no real <p> prose sweeps in nav labels,
    sidebars, and "related articles" headlines, which then match keywords the
    article itself never discusses. Measured against HN links, that fallback
    scored a story about a land-registry hack as mentioning "AI" 17 times.
    A miss is cheap here; a false match costs the user a bad digest entry.
    """
    cleaned = _DROP_BLOCKS_RE.sub(" ", html_text)

    paragraphs = [
        _WHITESPACE_RE.sub(" ", _TAG_RE.sub(" ", p)).strip()
        for p in _PARAGRAPH_RE.findall(cleaned)
    ]
    # Single-sentence <p> tags are usually captions, bylines, or cookie notices.
    return " ".join(p for p in paragraphs if len(p) > 80)
