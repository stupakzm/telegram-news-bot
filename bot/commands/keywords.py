import json
import re
import time

import db.client as db
import bot.telegram as tg

_MAX_KEYWORD_LEN = 64
_MAX_KEYWORDS = 50
_SPLIT_RE = re.compile(r"[\n,]+")

# Generic starter keywords offered as one-tap buttons during onboarding (UX-01).
# Kept short and colon-free so they fit Telegram's 64-byte callback_data limit.
SUGGESTED_KEYWORDS = [
    "AI", "security", "startup", "privacy",
    "open source", "GPU", "crypto", "cloud",
]


def suggested_keywords_markup() -> dict:
    """Inline keyboard of tappable starter keywords + a 'type my own' fallback."""
    rows: list[list[dict]] = []
    pair: list[dict] = []
    for kw in SUGGESTED_KEYWORDS:
        pair.append({"text": f"➕ {kw}", "callback_data": f"kw:sugg:{kw}"})
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([{"text": "⌨️ Type my own", "callback_data": "kw:add"}])
    return {"inline_keyboard": rows}


def _list_keywords(user_id: int) -> list[str]:
    rows = db.execute(
        "SELECT keyword FROM user_keywords WHERE user_id = ? ORDER BY added_at",
        [user_id],
    )
    return [r["keyword"] for r in rows]


def _build_view(user_id: int) -> tuple[str, dict]:
    keywords = _list_keywords(user_id)
    if keywords:
        lines = [f"• `{k}`" for k in keywords]
        text = (
            f"🎯 *Your Keywords* ({len(keywords)})\n\n"
            + "\n".join(lines)
            + "\n\nTap ❌ to remove, or ➕ to add more."
        )
    else:
        text = (
            "🎯 *Your Keywords*\n\n"
            "_No keywords set._\n\n"
            "Deliveries only include articles matching your keywords. "
            "Tap ➕ Add to set some (e.g. `AI, Tesla, GPU, security`)."
        )

    buttons = [
        [{"text": f"❌ {k[:40]}", "callback_data": f"kw:rm:{i}"}]
        for i, k in enumerate(keywords)
    ]
    buttons.append([{"text": "➕ Add keywords", "callback_data": "kw:add"}])
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

    db.execute_many([(
        "INSERT OR REPLACE INTO user_pending_actions (user_id, action, data, created_at) "
        "VALUES (?, 'keywords_add', '{}', ?)",
        [user_id, int(time.time())],
    )])

    tg.answer_callback_query(callback_query["id"])
    result = tg.send_message(
        chat_id=chat_id,
        text=(
            "Send keywords separated by commas or new lines.\n"
            "_e.g._ `AI, Tesla, GPU, supply chain`\n\n"
            "Matching is case-insensitive."
        ),
    )
    if result.get("message_id"):
        db.track_bot_message(user_id, result["message_id"])


def handle_suggest_callback(callback_query: dict, keyword: str) -> None:
    """Add a single suggested keyword in one tap (UX-01)."""
    user_id = callback_query["from"]["id"]
    keyword = keyword.strip()[:_MAX_KEYWORD_LEN]
    if not keyword:
        tg.answer_callback_query(callback_query["id"])
        return

    existing = set(_list_keywords(user_id))
    if keyword in existing:
        tg.answer_callback_query(callback_query["id"], text=f"Already added: {keyword}")
        return
    if len(existing) >= _MAX_KEYWORDS:
        tg.answer_callback_query(callback_query["id"], text=f"Max {_MAX_KEYWORDS} keywords reached.")
        return

    db.execute_many([(
        "INSERT OR IGNORE INTO user_keywords (user_id, keyword, added_at) VALUES (?, ?, ?)",
        [user_id, keyword, int(time.time())],
    )])
    tg.answer_callback_query(callback_query["id"], text=f"✅ Added: {keyword}")


def handle_remove_callback(callback_query: dict, index: int) -> None:
    user_id = callback_query["from"]["id"]
    msg = callback_query.get("message", {})
    chat_id = msg["chat"]["id"]
    message_id = msg["message_id"]

    keywords = _list_keywords(user_id)
    if 0 <= index < len(keywords):
        db.execute_many([(
            "DELETE FROM user_keywords WHERE user_id = ? AND keyword = ?",
            [user_id, keywords[index]],
        )])

    text, markup = _build_view(user_id)
    try:
        tg.edit_message_text(chat_id, message_id, text, reply_markup=markup)
    except Exception:
        pass
    tg.answer_callback_query(callback_query["id"], text="Removed.")


def handle_pending(message: dict, action: str, data_json: str) -> None:
    """Called by router when user has a pending keywords action."""
    user_id = message["from"]["id"]
    chat_id = message["chat"]["id"]
    raw = message.get("text", "")

    if action != "keywords_add":
        return

    candidates = [k.strip() for k in _SPLIT_RE.split(raw) if k.strip()]
    candidates = [k[:_MAX_KEYWORD_LEN] for k in candidates]

    if not candidates:
        tg.send_message(chat_id=chat_id, text="⚠️ No keywords found. Try again or send /keywords to cancel.")
        return

    existing = set(_list_keywords(user_id))
    total = len(existing)
    added: list[str] = []
    skipped: list[str] = []
    now = int(time.time())

    for k in candidates:
        if k in existing:
            skipped.append(k)
            continue
        if total + len(added) >= _MAX_KEYWORDS:
            skipped.append(k)
            continue
        added.append(k)

    if added:
        db.execute_many([
            (
                "INSERT OR IGNORE INTO user_keywords (user_id, keyword, added_at) VALUES (?, ?, ?)",
                [user_id, k, now],
            )
            for k in added
        ])

    db.execute_many([("DELETE FROM user_pending_actions WHERE user_id = ?", [user_id])])

    summary = [f"✅ Added {len(added)} keyword(s)."]
    if skipped:
        if total + len(added) >= _MAX_KEYWORDS:
            summary.append(f"⚠️ {len(skipped)} skipped (max {_MAX_KEYWORDS} keywords).")
        else:
            summary.append(f"⚠️ {len(skipped)} skipped (already present).")

    # One message: the outcome summary as a header on the refreshed list view
    # (avoids a separate summary message that duplicates the count).
    view_text, markup = _build_view(user_id)
    combined = "\n".join(summary) + "\n\n" + view_text
    result = tg.send_message(chat_id=chat_id, text=combined, reply_markup=markup)
    if result.get("message_id"):
        db.track_bot_message(user_id, result["message_id"])
