# bot/commands/clear.py
import db.client as db
import bot.telegram as tg


def handle(message: dict) -> None:
    """Delete all tracked bot response messages for this user."""
    user_id = message["from"]["id"]
    chat_id = message["chat"]["id"]

    rows = db.execute(
        "SELECT message_id FROM bot_messages WHERE user_id = ?", [user_id]
    )
    for row in rows:
        tg.delete_message(chat_id, row["message_id"])

    db.execute_many([
        ("DELETE FROM bot_messages WHERE user_id = ?", [user_id])
    ])
