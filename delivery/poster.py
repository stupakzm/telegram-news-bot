"""Format and send a single article to a user via Telegram."""
import hashlib
import logging
import os
import re
import time
from urllib.parse import urlsplit

import requests

from delivery.ratelimit import TokenBucket

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def _rate_cap() -> float:
    try:
        return float(os.environ.get("TELEGRAM_MAX_MSGS_PER_SEC", "25"))
    except ValueError:
        return 25.0


# Process-wide limiter shared by every delivery worker thread (DEL-01). Keeps the
# aggregate send rate under Telegram's global ceiling no matter the worker count.
_LIMITER = TokenBucket(_rate_cap())

# MarkdownV2 reserved characters that must be escaped outside entities.
_MDV2_SPECIAL = re.compile(r"([_*\[\]()~`>#+\-=|{}.!\\])")


def _escape_mdv2(text: str) -> str:
    return _MDV2_SPECIAL.sub(r"\\\1", text)


def _escape_mdv2_url(url: str) -> str:
    """Escape only the chars Telegram requires inside a MarkdownV2 link target."""
    return url.replace("\\", "\\\\").replace(")", "\\)")


def _url_key(url: str) -> str:
    """Short stable hash of the URL for use as Telegram callback_data."""
    return hashlib.md5(url.encode()).hexdigest()[:16]


def _source_domain(url: str) -> str:
    """Bare display domain for a URL, e.g. 'openai.com' (leading 'www.' dropped)."""
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _relative_age(published_at: int, now: float | None = None) -> str:
    """Human 'age' of a timestamp: 'just now', '3h ago', '2d ago'.

    Returns "" for a missing/zero timestamp or one in the future, so undated
    feed entries simply show no age rather than a wrong one.
    """
    if not published_at:
        return ""
    now = time.time() if now is None else now
    delta = int(now - published_at)
    if delta < 0:
        return ""
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{delta // 60}m ago"
    if delta < 86400:
        return f"{delta // 3600}h ago"
    return f"{delta // 86400}d ago"


def _source_line(url: str, published_at: int, now: float | None = None) -> str:
    """A subtle 'openai.com · 3h ago' line, MarkdownV2-escaped and italicised.

    Returns "" when there is no domain to show; the age is appended only when
    known so dated and undated entries both render cleanly.
    """
    domain = _source_domain(url)
    if not domain:
        return ""
    age = _relative_age(published_at, now)
    text = f"{domain} · {age}" if age else domain
    return f"_{_escape_mdv2(text)}_"


def _bot_url(method: str) -> str:
    return TELEGRAM_API.format(token=os.environ["TELEGRAM_BOT_TOKEN"], method=method)


def _send_message(
    chat_id: int,
    text: str,
    reply_to_message_id: int | None = None,
    reply_markup: dict | None = None,
) -> dict:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": True,
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    if reply_markup:
        payload["reply_markup"] = reply_markup

    _LIMITER.acquire()  # DEL-01: global rate limit across all worker threads
    resp = requests.post(_bot_url("sendMessage"), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()["result"]


def format_post(article: dict) -> str:
    """
    Article keys: url, title, summary, relevance (preformatted "Tesla-12, ...").
    relevance may be empty string when there are no matches (shouldn't happen
    in production since we filter score==0 upstream). Optional published_at
    (unix ts, 0/absent if unknown) drives the 'source · age' line.
    """
    title = _escape_mdv2(article["title"])
    url = _escape_mdv2_url(article["url"])
    summary = _escape_mdv2(article["summary"])

    lines = [f"\U0001f539 [*{title}*]({url})"]
    source = _source_line(article["url"], article.get("published_at") or 0)
    if source:
        lines.append(source)
    lines.append("")
    lines.append(summary)
    relevance = article.get("relevance", "")
    if relevance:
        lines.append("")
        lines.append(f"\U0001f3af {_escape_mdv2(relevance)}")
    return "\n".join(lines)


def post_article(user_id: int, article: dict, allow_followup: bool = True) -> None:
    """Send one article DM with thumbs reaction buttons, plus an importance follow-up.

    The 'why this matters' follow-up is sent only when ``allow_followup`` is True;
    callers cap how many go out per digest so the reader isn't buried in them.
    """
    text = format_post(article)
    url_key = _url_key(article["url"])
    reply_markup = {
        "inline_keyboard": [[
            {"text": "\U0001f44d", "callback_data": f"reaction:up:{url_key}"},
            {"text": "\U0001f44e", "callback_data": f"reaction:down:{url_key}"},
        ]]
    }
    result = _send_message(chat_id=user_id, text=text, reply_markup=reply_markup)

    if allow_followup and article.get("is_important") and article.get("importance_detail"):
        followup = f"\U0001f9f5 *Why this matters:*\n{_escape_mdv2(article['importance_detail'])}"
        try:
            _send_message(
                chat_id=user_id,
                text=followup,
                reply_to_message_id=result["message_id"],
            )
        except Exception as e:
            logger.warning("Failed to send importance followup to %d: %s", user_id, e)
