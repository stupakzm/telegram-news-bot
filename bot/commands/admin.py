import os
import time
import logging
import db.client as db
import bot.telegram as tg

logger = logging.getLogger(__name__)

_REFRESH_MARKUP = {"inline_keyboard": [
    [
        {"text": "\U0001f504 Refresh", "callback_data": "admin:refresh"},
        {"text": "\U0001f9f9 Clear errors", "callback_data": "admin:clear_errors"},
    ]
]}


def _build_status_text() -> str:
    now_ts = int(time.time())

    # Total registered users
    total_user_rows = db.execute("SELECT COUNT(*) as count FROM users")
    total_users = total_user_rows[0]["count"] if total_user_rows else 0

    # Active users in last 7 days
    active_rows = db.execute(
        "SELECT COUNT(DISTINCT user_id) as count FROM delivery_log WHERE sent_at > ? AND status = 'sent'",
        [now_ts - 7 * 24 * 3600]
    )
    active_users = active_rows[0]["count"] if active_rows else 0

    # Total deliveries all-time (helps diagnose if log is empty)
    total_delivery_rows = db.execute(
        "SELECT COUNT(*) as count, SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as sent_count FROM delivery_log"
    )
    total_deliveries = total_delivery_rows[0]["count"] if total_delivery_rows else 0
    total_sent = total_delivery_rows[0]["sent_count"] if total_delivery_rows and total_delivery_rows[0]["sent_count"] else 0

    # Deliveries in last hour
    delivery_rows = db.execute(
        "SELECT status, COUNT(*) as count FROM delivery_log WHERE sent_at > ? GROUP BY status",
        [now_ts - 3600]
    )
    sent_hour = next((r["count"] for r in delivery_rows if r["status"] == "sent"), 0)
    failed_hour = next((r["count"] for r in delivery_rows if r["status"] == "failed"), 0)

    # Total revenue in Stars
    revenue_rows = db.execute("SELECT SUM(stars_paid) as total FROM users")
    revenue = revenue_rows[0]["total"] if revenue_rows and revenue_rows[0]["total"] else 0

    # Recent errors from delivery_errors
    errors = db.execute(
        "SELECT theme_id, theme_type, error_msg, occurred_at "
        "FROM delivery_errors ORDER BY occurred_at DESC LIMIT 5"
    )

    error_lines = []
    if errors:
        for err in errors:
            err_dt = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(err["occurred_at"]))
            error_lines.append(
                f"\u2022 `[{err_dt}]` theme\\_id={err['theme_id']} \u2014 {err['error_msg']}"
            )
    else:
        error_lines = ["None"]

    refreshed_at = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(now_ts))
    return (
        f"\U0001f916 *Bot Status*\n\n"
        f"\U0001f465 *Total users:* {total_users}\n"
        f"\U0001f4ca *Active users (7d):* {active_users}\n"
        f"\U0001f4e6 *Total deliveries:* {total_deliveries} ({total_sent} sent)\n"
        f"\u26a1 *Last hour:* {sent_hour} sent"
        + (f", {failed_hour} failed" if failed_hour else "") + "\n"
        f"\U0001f4b0 *Revenue (Stars):* {revenue:,}\n\n"
        f"\u26a0\ufe0f *Recent errors:*\n" + "\n".join(error_lines) +
        f"\n\n_Updated: {refreshed_at}_"
    )


def handle(message: dict) -> None:
    """Handle /admin command. Shows bot health metrics. Owner only."""
    user_id = message["from"]["id"]
    chat_id = message["chat"]["id"]

    # Authorization (D-01): check OWNER_USER_ID env var
    owner_id = os.environ.get("OWNER_USER_ID")
    if not owner_id or user_id != int(owner_id):
        tg.send_message(chat_id=chat_id, text="Not authorized.")
        return

    text = _build_status_text()
    result = tg.send_message(chat_id=chat_id, text=text, reply_markup=_REFRESH_MARKUP)
    if result.get("message_id"):
        db.track_bot_message(user_id, result["message_id"])


def handle_refresh(callback_query: dict) -> None:
    """Handle admin:refresh callback — edit the existing panel in-place."""
    user_id = callback_query["from"]["id"]
    owner_id = os.environ.get("OWNER_USER_ID")
    if not owner_id or user_id != int(owner_id):
        tg.answer_callback_query(callback_query["id"], text="Not authorized.")
        return

    msg = callback_query.get("message", {})
    chat_id = msg["chat"]["id"]
    message_id = msg["message_id"]

    text = _build_status_text()
    try:
        tg.edit_message_text(chat_id, message_id, text, reply_markup=_REFRESH_MARKUP)
    except Exception as e:
        logger.warning("admin refresh edit failed: %s", e)
    tg.answer_callback_query(callback_query["id"])


def handle_clear_errors(callback_query: dict) -> None:
    """Handle admin:clear_errors callback — wipe delivery_errors and refresh panel."""
    user_id = callback_query["from"]["id"]
    owner_id = os.environ.get("OWNER_USER_ID")
    if not owner_id or user_id != int(owner_id):
        tg.answer_callback_query(callback_query["id"], text="Not authorized.")
        return

    db.execute_many([("DELETE FROM delivery_errors", [])])

    msg = callback_query.get("message", {})
    chat_id = msg["chat"]["id"]
    message_id = msg["message_id"]

    text = _build_status_text()
    try:
        tg.edit_message_text(chat_id, message_id, text, reply_markup=_REFRESH_MARKUP)
    except Exception as e:
        logger.warning("admin clear_errors edit failed: %s", e)
    tg.answer_callback_query(callback_query["id"], text="Errors cleared.")
