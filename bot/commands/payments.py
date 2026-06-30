"""Telegram Stars invoice + activation flow for VIP/SVIP plans.

Both plans are flat 30-day terms with no autorenew. When a user pays mid-plan
(renewal or tier switch), we replace their `tier_expires_at` with `now + 30d`
— no remaining-time rollover. Owner's call: simpler accounting; users renew
on a predictable cycle.
"""
import logging
import os
import time

import db.client as db
import bot.telegram as tg

logger = logging.getLogger(__name__)

PLAN_DURATION_SECONDS = 30 * 24 * 3600

_VALID_TIERS = ("vip", "svip")


def _price(tier: str) -> int:
    if tier == "vip":
        return int(os.environ.get("STARS_VIP_PRICE", "100"))
    if tier == "svip":
        return int(os.environ.get("STARS_SVIP_PRICE", "290"))
    raise ValueError(f"Unknown tier: {tier!r}")


def _title(tier: str) -> str:
    return "NewsBot VIP — 30 days" if tier == "vip" else "NewsBot SVIP — 30 days"


def _description(tier: str) -> str:
    if tier == "vip":
        return (
            "VIP — 7 RSS feeds, 2 deliveries per day, AI summaries filtered by "
            "your keywords. 30 days. No autorenew."
        )
    return (
        "SVIP — 15 RSS feeds, 4 deliveries per day, AI summaries filtered by "
        "your keywords. 30 days. No autorenew."
    )


def send_invoice(user_id: int, tier: str) -> None:
    """Send a Telegram Stars invoice. The user pays in their Telegram client."""
    if tier not in _VALID_TIERS:
        logger.warning("send_invoice: unknown tier %r for user %d", tier, user_id)
        return
    try:
        price = _price(tier)
    except ValueError:
        logger.error("send_invoice: bad tier price for %r", tier)
        return

    tg.send_invoice(
        chat_id=user_id,
        title=_title(tier),
        description=_description(tier),
        payload=f"tier:{tier}",
        currency="XTR",
        prices=[{"label": _title(tier), "amount": price}],
    )


def handle_successful_payment(message: dict) -> None:
    """Called by router when Telegram delivers a successful_payment update."""
    user_id = message["from"]["id"]
    payment = message.get("successful_payment", {})
    payload = payment.get("invoice_payload", "")

    if ":" not in payload:
        logger.error("handle_successful_payment: malformed payload %r for user %d", payload, user_id)
        tg.send_message(
            chat_id=user_id,
            text="⚠️ Payment received but could not be processed. Please contact support.",
        )
        return

    tier = payload.split(":", 1)[1]
    if tier not in _VALID_TIERS:
        logger.error("handle_successful_payment: unknown tier %r for user %d", tier, user_id)
        tg.send_message(
            chat_id=user_id,
            text="⚠️ Payment received but could not be processed. Please contact support.",
        )
        return

    amount = int(payment.get("total_amount", 0))
    now = int(time.time())
    expires_at = now + PLAN_DURATION_SECONDS

    db.execute_many([(
        "UPDATE users SET tier = ?, tier_expires_at = ?, stars_paid = stars_paid + ?, "
        "last_reminder_at = NULL WHERE user_id = ?",
        [tier, expires_at, amount, user_id],
    )])

    label = "VIP" if tier == "vip" else "SVIP"
    tg.send_message(
        chat_id=user_id,
        text=(
            f"🎉 *{label} activated!* 30 days of personalized news.\n"
            "Use /settings to verify, /timezone to set delivery hours, "
            "/keywords to tune your filter."
        ),
    )
