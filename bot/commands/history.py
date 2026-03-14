# bot/commands/history.py
import json
from datetime import datetime, timezone
import db.client as db
import bot.telegram as tg

MAX_HISTORY = 30


def handle(message: dict) -> None:
    user_id = message["from"]["id"]

    rows = db.execute("SELECT tier FROM users WHERE user_id = ?", [user_id])
    tier = rows[0]["tier"] if rows else "free"

    if tier != "monthly":
        tg.send_message(
            chat_id=user_id,
            text="📚 Digest history is available on the *Monthly plan*.\n\nUse /upgrade to unlock.",
        )
        return

    history = db.execute(
        "SELECT theme_name, articles, sent_at FROM digest_history "
        "WHERE user_id = ? ORDER BY sent_at DESC LIMIT ?",
        [user_id, MAX_HISTORY],
    )

    if not history:
        tg.send_message(chat_id=user_id, text="📭 No digest history yet. Check back after your first delivery.")
        return

    lines = []
    for row in history:
        dt = datetime.fromtimestamp(row["sent_at"], tz=timezone.utc).strftime("%b %d %H:%M UTC")
        articles = json.loads(row["articles"])
        titles = ", ".join(a["title"][:40] for a in articles[:2])
        lines.append(f"• *{row['theme_name']}* — {dt}\n  _{titles}_")

    text = "📚 *Your Digest History* (last 30)\n\n" + "\n\n".join(lines)
    tg.send_message(chat_id=user_id, text=text)
