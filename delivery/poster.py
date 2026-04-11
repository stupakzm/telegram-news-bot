import hashlib
import logging
import os
import re
import requests

logger = logging.getLogger(__name__)


def _url_key(url: str) -> str:
    """Return a 16-char hex hash of the URL for use as Telegram callback_data."""
    return hashlib.md5(url.encode()).hexdigest()[:16]

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

# Characters that must be escaped in MarkdownV2 (outside entities)
_MDV2_SPECIAL = re.compile(r"([_*\[\]()~`>#+\-=|{}.!\\])")


def _escape_mdv2(text: str) -> str:
    """Escape all MarkdownV2 special characters in plain text."""
    return _MDV2_SPECIAL.sub(r"\\\1", text)


def _bot_url(method: str) -> str:
    return TELEGRAM_API.format(token=os.environ["TELEGRAM_BOT_TOKEN"], method=method)


def _send_message(chat_id: int, text: str, reply_to_message_id: int = None, reply_markup: dict = None) -> dict:
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

    resp = requests.post(_bot_url("sendMessage"), json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["result"]


def format_post(article: dict) -> str:
    title = _escape_mdv2(article["title"])
    summary = _escape_mdv2(article["summary"])
    hashtags = _escape_mdv2(" ".join(article.get("hashtags", [])))
    url = article["url"]  # URLs inside [...](url) — the URL part is not escaped
    return (
        f"\U0001f539 *{title}*\n\n"
        f"{summary}\n\n"
        f"{hashtags}\n"
        f"\U0001f517 {_escape_mdv2(url)}"
    )


def send_already_received_note(user_id: int, theme_name: str, hashtag: str) -> None:
    """Notify user they already received today's digest for this theme."""
    tag = _escape_mdv2(hashtag)
    name = _escape_mdv2(theme_name)
    text = f"\u2705 You already received today's digest for *{name}* \\({tag}\\)\\. Check back tomorrow\\!"
    _send_message(chat_id=user_id, text=text)


def post_article(user_id: int, article: dict) -> None:
    """Send one article to a user's DM with reaction buttons. Sends a followup reply if important."""
    text = format_post(article)
    url_key = _url_key(article["url"])
    reply_markup = {
        "inline_keyboard": [[
            {"text": "\U0001f44d", "callback_data": f"reaction:up:{url_key}"},
            {"text": "\U0001f44e", "callback_data": f"reaction:down:{url_key}"}
        ]]
    }
    result = _send_message(chat_id=user_id, text=text, reply_markup=reply_markup)

    if article.get("is_important") and article.get("importance_detail"):
        followup = f"\U0001f9f5 *Why this matters:*\n{_escape_mdv2(article['importance_detail'])}"
        try:
            _send_message(
                chat_id=user_id,
                text=followup,
                reply_to_message_id=result["message_id"],
            )
        except Exception as e:
            logger.warning("Failed to send importance followup to user %d: %s", user_id, e)
