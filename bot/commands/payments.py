# bot/commands/payments.py
import logging
logger = logging.getLogger(__name__)
import os
import time
import db.client as db
import bot.telegram as tg

MONTHLY_DURATION = 30 * 24 * 3600  # 30 days


def send_invoice(user_id: int, tier: str) -> None:
    """Send a Stars payment invoice for one_time or monthly tier."""
    if tier == "one_time":
        price = int(os.environ.get("STARS_ONETIME_PRICE", "200"))
        title = "NewsBot — One-time Upgrade"
        description = "Unlock 6 themes, 1 custom theme, per-theme schedules. Yours forever."
    elif tier == "monthly":
        price = int(os.environ.get("STARS_MONTHLY_PRICE", "100"))
        title = "NewsBot — Monthly Subscription"
        description = "Unlock all features: 9 themes, 3 custom themes, digest history."
    else:
        raise ValueError(f"Unknown tier: {tier!r}")

    tg.send_invoice(
        chat_id=user_id,
        title=title,
        description=description,
        payload=f"tier:{tier}",
        currency="XTR",
        prices=[{"label": title, "amount": price}],
    )


def handle_successful_payment(message: dict) -> None:
    user_id = message["from"]["id"]
    payment = message["successful_payment"]
    payload = payment["invoice_payload"]  # e.g. "tier:one_time"
    if ":" not in payload:
        logger.error("handle_successful_payment: malformed payload %r for user %d", payload, user_id)
        tg.send_message(
            chat_id=user_id,
            text="⚠️ Payment received but could not be processed. Please contact support.",
        )
        return
    tier = payload.split(":", 1)[1]
    amount = payment["total_amount"]
    now = int(time.time())

    if tier == "one_time":
        db.execute_many([
            (
                "UPDATE users SET tier = ?, stars_paid = stars_paid + ? WHERE user_id = ?",
                ["one_time", amount, user_id],
            )
        ])
        tg.send_message(
            chat_id=user_id,
            text="🎉 *One-time upgrade activated!* You now have access to 6 themes and custom themes.",
        )
    elif tier == "monthly":
        expires_at = now + MONTHLY_DURATION
        db.execute_many([
            (
                "UPDATE users SET tier = ?, tier_expires_at = ?, stars_paid = stars_paid + ? "
                "WHERE user_id = ?",
                ["monthly", expires_at, amount, user_id],
            )
        ])
        tg.send_message(
            chat_id=user_id,
            text="🎉 *Monthly subscription activated!* All features unlocked for 30 days.",
        )
    else:
        logger.error(
            "handle_successful_payment: unknown tier %r in payload %r", tier, payload
        )
        tg.send_message(
            chat_id=user_id,
            text="⚠️ Payment received but could not be processed. Please contact support.",
        )
