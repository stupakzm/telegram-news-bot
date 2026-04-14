# bot/commands/addtheme.py
import json
import logging
import time
import feedparser
import requests as _requests
import db.client as db
import bot.telegram as tg
import google.generativeai as genai
import os
from bot.validation import validate_rss_url
from bot.config import UPGRADE_ENABLED

logger = logging.getLogger(__name__)

RSS_SUGGEST_PROMPT = """\
Suggest 4-5 high-quality RSS feed URLs for the topic: "{topic}"
Return ONLY a JSON array of objects, each with "name" (feed source name) and "url" (RSS URL).
Example: [{"name": "Example Blog", "url": "https://example.com/feed.xml"}]
No explanation, no markdown.
"""


def _suggest_feeds(topic: str) -> list[dict]:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-2.5-flash")
    resp = model.generate_content(RSS_SUGGEST_PROMPT.format(topic=topic))
    text = resp.text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


def _validate_feed(url: str) -> bool:
    if not validate_rss_url(url):
        return False
    try:
        resp = _requests.get(url, timeout=5, headers={"User-Agent": "feedparser"})
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        return len(feed.entries) > 0
    except Exception:
        return False


def _user_custom_theme_count(user_id: int) -> int:
    rows = db.execute(
        "SELECT COUNT(*) as c FROM user_themes WHERE user_id = ? AND theme_type = 'custom'",
        [user_id],
    )
    return rows[0]["c"] if rows else 0


def _tier_custom_limit(tier: str) -> int:
    return {"one_time": 1, "monthly": 3}.get(tier, 0)


def _check_access(user_id: int) -> tuple[bool, str]:
    rows = db.execute("SELECT tier FROM users WHERE user_id = ?", [user_id])
    tier = rows[0]["tier"] if rows else "free"
    if tier not in ("one_time", "monthly"):
        return False, "free"
    limit = _tier_custom_limit(tier)
    count = _user_custom_theme_count(user_id)
    if count >= limit:
        return False, tier
    return True, tier


def _set_pending(user_id: int, action: str, data: dict = None) -> None:
    db.execute_many([
        (
            "INSERT OR REPLACE INTO user_pending_actions (user_id, action, data, created_at) "
            "VALUES (?, ?, ?, ?)",
            [user_id, action, json.dumps(data or {}), int(time.time())],
        )
    ])


def _clear_pending(user_id: int) -> None:
    db.execute_many([
        ("DELETE FROM user_pending_actions WHERE user_id = ?", [user_id])
    ])


def _save_custom_theme(user_id: int, name: str, hashtag: str,
                        rss_feeds: list[str], ai_suggested: bool) -> None:
    """Insert custom theme into custom_themes and link it in user_themes."""
    # Atomic INSERT with RETURNING avoids TOCTOU race
    rows = db.execute(
        "INSERT INTO custom_themes (user_id, name, hashtag, rss_feeds, ai_suggested) "
        "VALUES (?, ?, ?, ?, ?) RETURNING id",
        [user_id, name, hashtag, json.dumps(rss_feeds), 1 if ai_suggested else 0],
    )
    custom_id = rows[0]["id"]
    db.execute_many([
        (
            "INSERT INTO user_themes (user_id, theme_type, theme_id, articles_per_theme) "
            "VALUES (?, 'custom', ?, 1)",
            [user_id, custom_id],
        )
    ])


def handle_ai(message: dict) -> None:
    """Step 1 of AI flow: prompt user to describe topic, set pending action."""
    user_id = message["from"]["id"]
    allowed, _ = _check_access(user_id)
    if not allowed:
        result = tg.send_message(chat_id=user_id, text=(
            "🔒 Custom themes require a paid plan. Use /upgrade." if UPGRADE_ENABLED
            else "🔒 Custom themes are coming soon. Stay tuned!"
        ))
        if result.get("message_id"):
            db.track_bot_message(user_id, result["message_id"])
        return
    _set_pending(user_id, "addtheme_ai_topic")
    result = tg.send_message(
        chat_id=user_id,
        text='🔍 *Add Custom Theme*\n\nDescribe the topic you want to follow:\n_(e.g. "electric vehicles", "NBA", "web security")_',
    )
    if result.get("message_id"):
        db.track_bot_message(user_id, result["message_id"])


def handle_manual(message: dict) -> None:
    """Step 1 of manual flow: prompt for RSS URLs, set pending action."""
    user_id = message["from"]["id"]
    allowed, _ = _check_access(user_id)
    if not allowed:
        result = tg.send_message(chat_id=user_id, text=(
            "🔒 Custom themes require a paid plan. Use /upgrade." if UPGRADE_ENABLED
            else "🔒 Custom themes are coming soon. Stay tuned!"
        ))
        if result.get("message_id"):
            db.track_bot_message(user_id, result["message_id"])
        return
    _set_pending(user_id, "addtheme_manual_urls")
    result = tg.send_message(
        chat_id=user_id,
        text="📋 *Add Custom Theme (Manual)*\n\nPaste RSS feed URLs, one per line:",
    )
    if result.get("message_id"):
        db.track_bot_message(user_id, result["message_id"])


def handle_pending(message: dict, action: str, data_json: str) -> None:
    """
    Called by router when user sends a non-command message and has a pending action.
    Routes to the correct step based on action value.
    """
    user_id = message["from"]["id"]
    text = message.get("text", "").strip()
    data = json.loads(data_json or "{}")

    if action == "addtheme_ai_topic":
        # User just sent the topic description → call AI, show feed choices
        try:
            feeds = _suggest_feeds(text)
        except Exception:
            result = tg.send_message(chat_id=user_id, text="❌ Could not fetch feed suggestions. Try again later.")
            if result.get("message_id"):
                db.track_bot_message(user_id, result["message_id"])
            _clear_pending(user_id)
            return
        buttons = [
            [{"text": f"{'✅' if i == 0 else '➕'} {f['name']}", "callback_data": f"addtheme:feed:{i}"}]
            for i, f in enumerate(feeds)
        ]
        buttons.append([{"text": "✅ Done — name this theme", "callback_data": "addtheme:feeds_done"}])
        _set_pending(user_id, "addtheme_ai_feeds", {"feeds": feeds, "selected": [0]})
        result = tg.send_message(
            chat_id=user_id,
            text="Here are suggested feeds. Tap to toggle, then tap Done:",
            reply_markup={"inline_keyboard": buttons},
        )
        if result.get("message_id"):
            db.track_bot_message(user_id, result["message_id"])

    elif action == "addtheme_ai_name":
        # User sent the theme name → save
        feeds = data.get("feeds", [])
        selected = data.get("selected", [0])
        urls = [feeds[i]["url"] for i in selected if i < len(feeds)]
        hashtag = "#" + text.lower().replace(" ", "")[:15]
        _save_custom_theme(user_id, text, hashtag, urls, ai_suggested=True)
        _clear_pending(user_id)
        result = tg.send_message(chat_id=user_id, text=f"✅ Theme *{text}* added! Use /themes to manage it.")
        if result.get("message_id"):
            db.track_bot_message(user_id, result["message_id"])

    elif action == "addtheme_manual_urls":
        # User sent RSS URLs → validate, ask for name
        urls = [line.strip() for line in text.splitlines() if line.strip().startswith("http")]
        if not urls:
            result = tg.send_message(chat_id=user_id, text="❌ No valid URLs found. Send URLs starting with http.")
            if result.get("message_id"):
                db.track_bot_message(user_id, result["message_id"])
            return
        # Filter out restricted URLs
        blocked = [u for u in urls if not validate_rss_url(u)]
        if blocked:
            result = tg.send_message(chat_id=user_id, text="❌ That URL uses a restricted address and cannot be used as an RSS feed.")
            if result.get("message_id"):
                db.track_bot_message(user_id, result["message_id"])
            urls = [u for u in urls if validate_rss_url(u)]
            if not urls:
                return
        valid = [u for u in urls if _validate_feed(u)]
        if not valid:
            result = tg.send_message(chat_id=user_id, text="❌ None returned valid RSS entries. Check URLs and retry.")
            if result.get("message_id"):
                db.track_bot_message(user_id, result["message_id"])
            return
        _set_pending(user_id, "addtheme_manual_name", {"urls": valid})
        result = tg.send_message(
            chat_id=user_id,
            text=f"✅ {len(valid)} feed(s) validated. What should this theme be called?",
        )
        if result.get("message_id"):
            db.track_bot_message(user_id, result["message_id"])

    elif action == "addtheme_manual_name":
        # User sent the theme name → save
        urls = data.get("urls", [])
        hashtag = "#" + text.lower().replace(" ", "")[:15]
        _save_custom_theme(user_id, text, hashtag, urls, ai_suggested=False)
        _clear_pending(user_id)
        result = tg.send_message(chat_id=user_id, text=f"✅ Theme *{text}* added! Use /themes to manage it.")
        if result.get("message_id"):
            db.track_bot_message(user_id, result["message_id"])

    else:
        logger.warning("handle_pending: unknown action %r for user %d", action, user_id)
        _clear_pending(user_id)
        result = tg.send_message(chat_id=user_id, text="⚠️ Something went wrong. Please try your command again.")
        if result.get("message_id"):
            db.track_bot_message(user_id, result["message_id"])


def toggle_feed(user_id: int, feed_idx: int) -> None:
    """Toggle a feed selection in the addtheme_ai_feeds pending state."""
    rows = db.execute(
        "SELECT data FROM user_pending_actions WHERE user_id = ? AND action = 'addtheme_ai_feeds'",
        [user_id],
    )
    if not rows:
        return
    data = json.loads(rows[0]["data"])
    selected: list = data.get("selected", [])
    if feed_idx in selected:
        selected.remove(feed_idx)
    else:
        selected.append(feed_idx)
    data["selected"] = selected
    _set_pending(user_id, "addtheme_ai_feeds", data)

    # Redraw buttons with updated checkmarks
    feeds = data.get("feeds", [])
    buttons = [
        [{"text": f"{'✅' if i in selected else '➕'} {f['name']}", "callback_data": f"addtheme:feed:{i}"}]
        for i, f in enumerate(feeds)
    ]
    buttons.append([{"text": "✅ Done — name this theme", "callback_data": "addtheme:feeds_done"}])
    result = tg.send_message(
        chat_id=user_id,
        text="Toggle feeds, then tap Done:",
        reply_markup={"inline_keyboard": buttons},
    )
    if result.get("message_id"):
        db.track_bot_message(user_id, result["message_id"])


def feeds_done(user_id: int) -> None:
    """User confirmed feed selection → ask for theme name."""
    rows = db.execute(
        "SELECT data FROM user_pending_actions WHERE user_id = ? AND action = 'addtheme_ai_feeds'",
        [user_id],
    )
    if not rows:
        return
    data = json.loads(rows[0]["data"])
    selected = data.get("selected", [])
    if not selected:
        result = tg.send_message(chat_id=user_id, text="⚠️ Please select at least one feed before continuing.")
        if result.get("message_id"):
            db.track_bot_message(user_id, result["message_id"])
        return
    _set_pending(user_id, "addtheme_ai_name", data)
    result = tg.send_message(
        chat_id=user_id,
        text='What should this theme be called? _(e.g. "Electric Vehicles")_',
    )
    if result.get("message_id"):
        db.track_bot_message(user_id, result["message_id"])
