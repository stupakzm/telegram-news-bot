"""
Delivery orchestrator — invoked hourly by GitHub Actions.

Per-user pipeline:
  fetch each feed → score in code → upsert into per-user pool →
  pick top-2 per URL (score > 0) → batch AI summary → post via Telegram.

No shared cache: each user's URL+keyword combination is unique, so cache hits
would be near zero. Will revisit if/when feed URLs deduplicate across many
users.
"""
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()  # ensure env is loaded before project imports that read os.environ at import time

from bot.logging_config import setup as setup_logging
setup_logging()

logger = logging.getLogger(__name__)

import db.client as db
from delivery.scheduler import (
    get_due_users,
    user_today_start_utc_ts,
    cleanup_seen_articles,
    check_expiry_reminders,
)
from delivery.fetcher import fetch_today_articles
from delivery.scoring import score_article, format_relevance
from delivery.ai import summarize_articles
from delivery.poster import post_article

_MAX_USER_WORKERS = 5
_TELEGRAM_FLOOD_PAUSE = 0.1


def _load_feeds(user_id: int) -> list[str]:
    rows = db.execute(
        "SELECT url FROM user_feeds WHERE user_id = ? ORDER BY added_at",
        [user_id],
    )
    return [r["url"] for r in rows]


def _load_keywords(user_id: int) -> list[str]:
    rows = db.execute(
        "SELECT keyword FROM user_keywords WHERE user_id = ? ORDER BY added_at",
        [user_id],
    )
    return [r["keyword"] for r in rows]


def _recent_sent_urls(user_id: int, since_ts: int) -> set[str]:
    rows = db.execute(
        "SELECT article_url FROM delivery_log "
        "WHERE user_id = ? AND sent_at > ? AND status = 'sent'",
        [user_id, since_ts],
    )
    return {r["article_url"] for r in rows}


def _existing_seen_urls(user_id: int) -> set[str]:
    rows = db.execute(
        "SELECT article_url FROM seen_articles WHERE user_id = ?",
        [user_id],
    )
    return {r["article_url"] for r in rows}


def _write_feed_errors(user_id: int, errors: list[tuple[str, str]], now_ts: int) -> None:
    if not errors:
        return
    try:
        db.execute_many([
            (
                "INSERT INTO delivery_errors (user_id, feed_url, error_msg, occurred_at) "
                "VALUES (?, ?, ?, ?)",
                [user_id, feed_url, err, now_ts],
            )
            for feed_url, err in errors
        ])
    except Exception as e:
        logger.warning("Failed to write delivery_errors for %d: %s", user_id, e)


def _deliver_user(user: dict, now_utc: datetime) -> dict:
    user_id = user["user_id"]
    tz = user["timezone"]
    now_ts = int(now_utc.timestamp())
    today_start_ts = user_today_start_utc_ts(tz, now_utc)

    feeds = _load_feeds(user_id)
    keywords = _load_keywords(user_id)
    if not feeds or not keywords:
        logger.info(
            "skip user=%d reason=no_config feeds=%d keywords=%d",
            user_id, len(feeds), len(keywords),
        )
        return {"user_id": user_id, "status": "no_config", "sent": 0, "failed": 0}

    recent_sent = _recent_sent_urls(user_id, now_ts - 24 * 3600)
    seen_urls = _existing_seen_urls(user_id)

    fetch_errors: list[tuple[str, str]] = []
    new_rows: list[tuple] = []

    for feed_url in feeds:
        try:
            articles = fetch_today_articles(feed_url, today_start_ts)
        except Exception as e:
            fetch_errors.append((feed_url, f"{type(e).__name__}: {e}"))
            continue

        for article in articles:
            url = article["url"]
            if url in recent_sent or url in seen_urls:
                continue
            score, breakdown = score_article(article["title"], article["body"], keywords)
            new_rows.append((
                "INSERT OR IGNORE INTO seen_articles "
                "(user_id, feed_url, article_url, article_title, article_body, "
                "score, match_breakdown, fetched_at, sent_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                [
                    user_id, feed_url, url, article["title"], article["body"],
                    score, json.dumps(breakdown), now_ts,
                ],
            ))
            seen_urls.add(url)

    if new_rows:
        try:
            db.execute_many(new_rows)
        except Exception as e:
            logger.error("Failed to insert seen_articles for %d: %s", user_id, e)

    pool = db.execute(
        "SELECT id, feed_url, article_url, article_title, article_body, score, match_breakdown "
        "FROM seen_articles "
        "WHERE user_id = ? AND sent_at IS NULL AND score > 0 "
        "ORDER BY score DESC",
        [user_id],
    )

    by_feed: dict[str, list[dict]] = {}
    for row in pool:
        by_feed.setdefault(row["feed_url"], []).append(row)

    selected: list[dict] = []
    for feed_url in feeds:
        selected.extend(by_feed.get(feed_url, [])[:2])

    if not selected:
        _write_feed_errors(user_id, fetch_errors, now_ts)
        logger.info(
            "user=%d feeds=%d keywords=%d new_seen=%d sent=0 status=no_matches",
            user_id, len(feeds), len(keywords), len(new_rows),
        )
        return {"user_id": user_id, "status": "no_matches", "sent": 0, "failed": 0}

    ai_inputs = [
        {"url": s["article_url"], "title": s["article_title"], "body": s["article_body"]}
        for s in selected
    ]
    summaries = summarize_articles(ai_inputs)
    summary_by_url = {s["url"]: s for s in summaries}

    sent = 0
    failed = 0
    update_stmts: list[tuple] = []

    for s in selected:
        ai = summary_by_url.get(s["article_url"])
        if not ai:
            # AI flagged skip=true, or this article fell off after a provider retry
            continue
        try:
            breakdown = json.loads(s["match_breakdown"])
        except (json.JSONDecodeError, TypeError):
            breakdown = {}
        article = {
            "url": s["article_url"],
            "title": s["article_title"],
            "summary": ai.get("summary", ""),
            "is_important": ai.get("is_important"),
            "importance_detail": ai.get("importance_detail", ""),
            "relevance": format_relevance(breakdown),
        }
        try:
            post_article(user_id=user_id, article=article)
            sent += 1
            update_stmts.append((
                "UPDATE seen_articles SET sent_at = ? WHERE id = ?",
                [now_ts, s["id"]],
            ))
            update_stmts.append((
                "INSERT INTO delivery_log (user_id, article_url, status, sent_at) "
                "VALUES (?, ?, 'sent', ?)",
                [user_id, s["article_url"], now_ts],
            ))
            time.sleep(_TELEGRAM_FLOOD_PAUSE)
        except Exception as e:
            failed += 1
            logger.error("post_article failed user=%d url=%s err=%s", user_id, s["article_url"], e)
            update_stmts.append((
                "INSERT INTO delivery_log (user_id, article_url, status, sent_at) "
                "VALUES (?, ?, 'failed', ?)",
                [user_id, s["article_url"], now_ts],
            ))

    if update_stmts:
        try:
            db.execute_many(update_stmts)
        except Exception as e:
            logger.error("Failed to persist delivery state for %d: %s", user_id, e)

    _write_feed_errors(user_id, fetch_errors, now_ts)

    logger.info(
        "user=%d feeds=%d keywords=%d new_seen=%d sent=%d failed=%d status=ok",
        user_id, len(feeds), len(keywords), len(new_rows), sent, failed,
    )
    return {"user_id": user_id, "status": "ok", "sent": sent, "failed": failed}


def _deliver_safely(user: dict, now_utc: datetime) -> dict:
    try:
        return _deliver_user(user, now_utc)
    except Exception as e:
        logger.exception("Unhandled delivery error for user %d: %s", user["user_id"], e)
        try:
            db.execute_many([(
                "INSERT INTO delivery_errors (user_id, feed_url, error_msg, occurred_at) "
                "VALUES (?, NULL, ?, ?)",
                [user["user_id"], f"unhandled: {e}", int(now_utc.timestamp())],
            )])
        except Exception:
            pass
        return {"user_id": user["user_id"], "status": "error", "sent": 0, "failed": 0}


def run() -> None:
    now_utc = datetime.now(timezone.utc)
    run_start = time.monotonic()
    logger.info("run start hour_utc=%d", now_utc.hour)

    due = get_due_users(now_utc)
    if not due:
        logger.info("run skip: no users due this hour")
        check_expiry_reminders()
        cleanup_seen_articles()
        return

    logger.info("processing %d due user(s)", len(due))

    with ThreadPoolExecutor(max_workers=_MAX_USER_WORKERS) as executor:
        results = list(executor.map(lambda u: _deliver_safely(u, now_utc), due))

    sent_total = sum(r["sent"] for r in results)
    failed_total = sum(r["failed"] for r in results)
    errors_total = sum(1 for r in results if r["status"] == "error")
    duration = time.monotonic() - run_start
    logger.info(
        "run complete users=%d sent=%d failed=%d errors=%d duration=%.1fs",
        len(due), sent_total, failed_total, errors_total, duration,
    )

    check_expiry_reminders()
    cleanup_seen_articles()


if __name__ == "__main__":
    run()
