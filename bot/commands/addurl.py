import logging
import time

import feedparser
import requests as _requests

import db.client as db
import bot.telegram as tg
from bot.validation import validate_rss_url

logger = logging.getLogger(__name__)

_QUOTA_BY_TIER = {"svip": 15, "vip": 7, "trial": 7, "expired": 7}
_DEFAULT_QUOTA = 7


def _quota_for(tier: str) -> int:
    return _QUOTA_BY_TIER.get(tier, _DEFAULT_QUOTA)


def _user_tier(user_id: int) -> str:
    rows = db.execute("SELECT tier FROM users WHERE user_id = ?", [user_id])
    return rows[0]["tier"] if rows else "expired"


def _list_feeds(user_id: int) -> list[dict]:
    return db.execute(
        "SELECT id, url FROM user_feeds WHERE user_id = ? ORDER BY added_at",
        [user_id],
    )


def _validate_feed(url: str) -> tuple[bool, str]:
    """Returns (ok, reason). reason is empty on success."""
    if not validate_rss_url(url):
        return False, "restricted address"
    try:
        resp = _requests.get(url, timeout=8, headers={"User-Agent": "newsbot/1.0"})
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        if not feed.entries:
            return False, "no RSS entries"
        return True, ""
    except _requests.exceptions.RequestException as e:
        return False, f"fetch failed ({type(e).__name__})"
    except Exception as e:
        logger.warning("addurl validate %s: %s", url, e)
        return False, "parse error"


def _build_view(user_id: int) -> tuple[str, dict]:
    tier = _user_tier(user_id)
    quota = _quota_for(tier)
    feeds = _list_feeds(user_id)

    if feeds:
        lines = [f"{i+1}. `{f['url'][:60]}`" for i, f in enumerate(feeds)]
        body = "\n".join(lines)
    else:
        body = "_No feeds yet._"

    text = (
        f"📰 *Your RSS Feeds* ({len(feeds)}/{quota})\n\n"
        f"{body}\n\n"
        "Tap ❌ to remove, or ➕ to add."
    )
    buttons = [
        [{"text": f"❌ {f['url'][:50]}", "callback_data": f"url:rm:{f['id']}"}]
        for f in feeds
    ]
    if len(feeds) < quota:
        buttons.append([{"text": "➕ Add URL", "callback_data": "url:add"}])
    else:
        text += f"\n\n⚠️ At quota ({quota}). Upgrade to SVIP for 15."
    return text, {"inline_keyboard": buttons}


def handle(message: dict) -> None:
    user_id = message["from"]["id"]
    chat_id = message["chat"]["id"]
    text, markup = _build_view(user_id)
    result = tg.send_message(chat_id=chat_id, text=text, reply_markup=markup)
    if result.get("message_id"):
        db.track_bot_message(user_id, result["message_id"])


def handle_add_callback(callback_query: dict) -> None:
    user_id = callback_query["from"]["id"]
    msg = callback_query.get("message", {})
    chat_id = msg.get("chat", {}).get("id", user_id)

    quota = _quota_for(_user_tier(user_id))
    current = len(_list_feeds(user_id))
    if current >= quota:
        tg.answer_callback_query(callback_query["id"], text="At quota.")
        return

    db.execute_many([(
        "INSERT OR REPLACE INTO user_pending_actions (user_id, action, data, created_at) "
        "VALUES (?, 'addurl_paste', '{}', ?)",
        [user_id, int(time.time())],
    )])
    tg.answer_callback_query(callback_query["id"])
    result = tg.send_message(
        chat_id=chat_id,
        text=(
            "Paste one or more RSS feed URLs, one per line.\n"
            "I'll validate each before adding.\n\n"
            f"_Remaining slots: {quota - current}_"
        ),
    )
    if result.get("message_id"):
        db.track_bot_message(user_id, result["message_id"])


def handle_remove_callback(callback_query: dict, feed_id: int) -> None:
    user_id = callback_query["from"]["id"]
    msg = callback_query.get("message", {})
    chat_id = msg["chat"]["id"]
    message_id = msg["message_id"]

    db.execute_many([(
        "DELETE FROM user_feeds WHERE id = ? AND user_id = ?",
        [feed_id, user_id],
    )])
    text, markup = _build_view(user_id)
    try:
        tg.edit_message_text(chat_id, message_id, text, reply_markup=markup)
    except Exception:
        pass
    tg.answer_callback_query(callback_query["id"], text="Removed.")


def handle_pending(message: dict, action: str, data_json: str) -> None:
    """Validate and add URLs the user pasted after tapping ➕ Add URL."""
    user_id = message["from"]["id"]
    chat_id = message["chat"]["id"]
    raw = message.get("text", "")

    if action != "addurl_paste":
        return

    candidates = [u.strip() for u in raw.splitlines() if u.strip().startswith("http")]
    if not candidates:
        tg.send_message(
            chat_id=chat_id,
            text="⚠️ No URLs found. Paste URLs starting with http(s), one per line.",
        )
        return

    tier = _user_tier(user_id)
    quota = _quota_for(tier)
    existing_urls = {f["url"] for f in _list_feeds(user_id)}
    remaining = quota - len(existing_urls)

    added: list[str] = []
    failed: list[tuple[str, str]] = []
    duplicates: list[str] = []
    now = int(time.time())

    for url in candidates:
        if url in existing_urls or url in added:
            duplicates.append(url)
            continue
        if len(added) >= remaining:
            failed.append((url, "quota reached"))
            continue
        ok, reason = _validate_feed(url)
        if not ok:
            failed.append((url, reason))
            continue
        added.append(url)

    if added:
        db.execute_many([
            (
                "INSERT OR IGNORE INTO user_feeds (user_id, url, added_at) VALUES (?, ?, ?)",
                [user_id, url, now],
            )
            for url in added
        ])

    db.execute_many([("DELETE FROM user_pending_actions WHERE user_id = ?", [user_id])])

    lines = [f"✅ Added {len(added)} feed(s)."]
    if duplicates:
        lines.append(f"⚠️ {len(duplicates)} duplicate(s) skipped.")
    for url, reason in failed:
        lines.append(f"❌ `{url[:60]}` — {reason}")

    result = tg.send_message(chat_id=chat_id, text="\n".join(lines))
    if result.get("message_id"):
        db.track_bot_message(user_id, result["message_id"])

    text, markup = _build_view(user_id)
    result = tg.send_message(chat_id=chat_id, text=text, reply_markup=markup)
    if result.get("message_id"):
        db.track_bot_message(user_id, result["message_id"])
