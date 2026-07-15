"""`/help` — list every user-facing command.

Renders from bot.set_commands.PUBLIC_COMMANDS so the menu (setMyCommands),
the help text, and the actual routes stay in sync.
"""
import db.client as db
import bot.telegram as tg
from bot.set_commands import PUBLIC_COMMANDS


def handle(message: dict) -> None:
    user_id = message["from"]["id"]
    chat_id = message["chat"]["id"]

    lines = ["🤖 *NewsBot commands*", ""]
    lines += [f"• /{cmd} — {desc}" for cmd, desc in PUBLIC_COMMANDS]
    lines += [
        "",
        "Deliveries need at least one *feed* (/addurl) and one *keyword* "
        "(/keywords). Set your /timezone so digests arrive at the right hour.",
    ]
    text = "\n".join(lines)

    result = tg.send_message(chat_id=chat_id, text=text)
    if result.get("message_id"):
        db.track_bot_message(user_id, result["message_id"])
