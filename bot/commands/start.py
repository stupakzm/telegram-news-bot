import time
import db.client as db
import bot.telegram as tg
from bot.config import UPGRADE_ENABLED

WELCOME = """\
👋 *Welcome to NewsBot!*

I deliver personalized news digests straight to your DMs — summarized by AI, on your schedule.

*Free tier includes:*
• Up to 5 topic themes
• 1 article per theme per digest
• Custom delivery schedule (days + time)

Use the buttons below to get started, or type /upgrade to see paid options.
"""

WELCOME_NO_UPGRADE = """\
👋 *Welcome to NewsBot!*

I deliver personalized news digests straight to your DMs — summarized by AI, on your schedule.

*What you get:*
• Up to 5 topic themes
• 1 article per theme per digest
• Custom delivery schedule (days + time)

Use the buttons below to get started. More features coming soon!
"""


def handle(message: dict) -> None:
    user_id = message["from"]["id"]

    # Register user if not exists
    existing = db.execute("SELECT user_id FROM users WHERE user_id = ?", [user_id])
    if not existing:
        db.execute_many([
            (
                "INSERT INTO users (user_id, tier, created_at, stars_paid) VALUES (?, 'free', ?, 0)",
                [user_id, int(time.time())],
            )
        ])

    if UPGRADE_ENABLED:
        text = WELCOME
        keyboard = {
            "inline_keyboard": [
                [{"text": "📰 Browse Themes", "callback_data": "themes:browse"}],
                [{"text": "⏰ Set Schedule", "callback_data": "schedule:setup"}],
                [{"text": "⭐ View Paid Plans", "callback_data": "upgrade:show"}],
            ]
        }
    else:
        text = WELCOME_NO_UPGRADE
        keyboard = {
            "inline_keyboard": [
                [{"text": "📰 Browse Themes", "callback_data": "themes:browse"}],
                [{"text": "⏰ Set Schedule", "callback_data": "schedule:setup"}],
            ]
        }
    tg.send_message(chat_id=user_id, text=text, reply_markup=keyboard)
