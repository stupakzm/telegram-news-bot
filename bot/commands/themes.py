# bot/commands/themes.py
import db.client as db
import bot.telegram as tg
from bot.config import UPGRADE_ENABLED

TIER_THEME_LIMITS = {"free": 5, "one_time": 6, "monthly": 9}


def _get_user_tier(user_id: int) -> str:
    """Return user's tier. Uses .get() so any row shape is tolerated."""
    rows = db.execute("SELECT tier FROM users WHERE user_id = ?", [user_id])
    return rows[0].get("tier", "free") if rows else "free"


def _get_user_theme_count(user_id: int) -> int:
    """Return count of user's theme subscriptions via len(rows)."""
    rows = db.execute(
        "SELECT theme_type, theme_id FROM user_themes WHERE user_id = ?", [user_id]
    )
    return len(rows)


def _get_user_theme_ids(user_id: int) -> set:
    """Return set of (theme_type, theme_id) tuples for user's subscriptions."""
    rows = db.execute(
        "SELECT theme_type, theme_id FROM user_themes WHERE user_id = ?", [user_id]
    )
    return {(r["theme_type"], r["theme_id"]) for r in rows}


def add_theme(user_id: int, theme_type: str, theme_id: int) -> bool:
    """Add a theme subscription. Returns True if added, False if at limit."""
    tier = _get_user_tier(user_id)  # first DB call
    limit = TIER_THEME_LIMITS.get(tier, 5)

    count = _get_user_theme_count(user_id)  # second DB call
    if count >= limit:
        msg = (
            f"You've reached the {limit}-theme limit for your plan. Use /upgrade to add more themes."
            if UPGRADE_ENABLED else
            f"You've reached the {limit}-theme limit for your plan. More options coming soon!"
        )
        result = tg.send_message(chat_id=user_id, text=msg)
        if result.get("message_id"):
            db.track_bot_message(user_id, result["message_id"])
        return False

    articles = 2 if tier == "monthly" else 1
    db.execute_many([
        (
            "INSERT INTO user_themes (user_id, theme_type, theme_id, articles_per_theme) "
            "VALUES (?, ?, ?, ?)",
            [user_id, theme_type, theme_id, articles],
        )
    ])
    return True


def remove_theme(user_id: int, theme_type: str, theme_id: int) -> None:
    """Remove a theme subscription."""
    db.execute_many([
        (
            "DELETE FROM user_themes WHERE user_id = ? AND theme_type = ? AND theme_id = ?",
            [user_id, theme_type, theme_id],
        )
    ])


def _build_keyboard(user_id: int) -> dict:
    """Build the themes inline keyboard for a user."""
    all_themes = db.execute(
        "SELECT id, name, hashtag FROM themes WHERE is_active = 1 ORDER BY id"
    )
    subscribed = _get_user_theme_ids(user_id)

    buttons = []
    for t in all_themes:
        is_sub = ("default", t["id"]) in subscribed
        label = f"{'✅' if is_sub else '➕'} {t['name']} {t['hashtag']}"
        action = "remove" if is_sub else "add"
        buttons.append([{
            "text": label,
            "callback_data": f"themes:{action}:default:{t['id']}",
        }])

    tier_rows = db.execute("SELECT tier FROM users WHERE user_id = ?", [user_id])
    tier = tier_rows[0].get("tier", "free") if tier_rows else "free"
    if tier in ("one_time", "monthly"):
        buttons.append([{"text": "➕ Add Custom Theme (AI)", "callback_data": "addtheme:ai"}])
        buttons.append([{"text": "➕ Add Custom Theme (Manual)", "callback_data": "addtheme:manual"}])

    return {"inline_keyboard": buttons}


def refresh_keyboard(user_id: int, chat_id: int, message_id: int) -> None:
    """Update the themes keyboard in-place after a subscribe/unsubscribe action."""
    tg.edit_message_reply_markup(chat_id, message_id, _build_keyboard(user_id))


def handle(message: dict) -> None:
    """Show user's theme subscriptions with inline toggle buttons."""
    user_id = message["from"]["id"]
    chat_id = message["chat"]["id"]

    result = tg.send_message(
        chat_id=chat_id,
        text="*Your Themes*\n\nTap a theme to subscribe or unsubscribe:",
        reply_markup=_build_keyboard(user_id),
    )
    if result.get("message_id"):
        db.track_bot_message(user_id, result["message_id"])
