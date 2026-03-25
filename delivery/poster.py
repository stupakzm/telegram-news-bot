import os
import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def _bot_url(method: str) -> str:
    return TELEGRAM_API.format(token=os.environ["TELEGRAM_BOT_TOKEN"], method=method)


def _send_message(chat_id: int, text: str, reply_to_message_id: int = None, reply_markup: dict = None) -> dict:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
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
    hashtags = " ".join(article.get("hashtags", []))
    return (
        f"🔹 *{article['title']}*\n\n"
        f"{article['summary']}\n\n"
        f"{hashtags}\n"
        f"🔗 {article['url']}"
    )


def post_article(user_id: int, article: dict) -> None:
    """Send one article to a user's DM with reaction buttons. Sends a followup reply if important."""
    text = format_post(article)
    reply_markup = {
        "inline_keyboard": [[
            {"text": "\U0001f44d", "callback_data": f"reaction:up:{article['url']}"},
            {"text": "\U0001f44e", "callback_data": f"reaction:down:{article['url']}"}
        ]]
    }
    result = _send_message(chat_id=user_id, text=text, reply_markup=reply_markup)

    if article.get("is_important") and article.get("importance_detail"):
        followup = f"🧵 *Why this matters:*\n{article['importance_detail']}"
        _send_message(
            chat_id=user_id,
            text=followup,
            reply_to_message_id=result["message_id"],
        )
