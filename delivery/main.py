# delivery/main.py
"""
Main delivery orchestrator. Called by GitHub Actions every hour.
Usage: python -m delivery.main
"""
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()  # load env BEFORE project imports that may read env at import time

from bot.logging_config import setup as setup_logging
setup_logging()

logger = logging.getLogger(__name__)

import db.client as db
from delivery.scheduler import get_due_deliveries, group_by_theme, check_expiry_reminders
from delivery.fetcher import fetch_articles
from delivery.ai import summarize_articles
from delivery import cache as theme_cache
from delivery.poster import post_article, send_already_received_note

# Max parallel theme workers. Bounded to avoid hammering Telegram/AI APIs simultaneously.
_MAX_THEME_WORKERS = 5


def get_theme_info(theme_type: str, theme_id: int) -> dict | None:
    """Fetch theme details (name, hashtag, rss_feeds) from DB."""
    if theme_type == "default":
        rows = db.execute(
            "SELECT id, name, hashtag, rss_feeds FROM themes WHERE id = ? AND is_active = 1",
            [theme_id],
        )
    else:
        rows = db.execute(
            "SELECT id, name, hashtag, rss_feeds FROM custom_themes WHERE id = ?",
            [theme_id],
        )
    if not rows:
        return None
    row = rows[0]
    return {
        "id": row["id"],
        "theme_type": theme_type,
        "name": row["name"],
        "hashtag": row["hashtag"],
        "rss_feeds": json.loads(row["rss_feeds"]),
    }


def _process_theme(
    theme_type: str,
    theme_id: int,
    users: list[dict],
    now_ts: int,
) -> dict:
    """
    Process a single theme: fetch, summarize, post.
    Returns a result dict with counters, sent articles, delivery log statements, and theme info.
    """
    status = "ok"
    articles_fetched = 0
    articles_sent = 0
    error_msg = None
    theme_name = "unknown"
    user_count = len(users)
    sent_articles: list[dict] = []
    delivery_log_statements: list[tuple] = []
    posted_urls: list[str] = []
    theme_info: dict | None = None

    try:
        theme = get_theme_info(theme_type, theme_id)
        if not theme:
            status = "error"
            error_msg = "theme not found"
            logger.warning("Theme not found: theme_type=%s theme_id=%d", theme_type, theme_id)
            return _build_result(
                theme_type, theme_id, theme_name, user_count,
                status, articles_fetched, articles_sent, error_msg,
                theme_info, sent_articles, delivery_log_statements, posted_urls,
            )

        theme_name = theme["name"]
        theme_info = theme

        # Rolling 24h article pool — score only genuinely new articles, deliver from full pool
        pool = theme_cache.get_pool(theme_type, theme_id)
        existing_urls = {a["url"] for a in pool}

        raw_articles = fetch_articles(theme)
        new_raw = [a for a in raw_articles if a["url"] not in existing_urls]
        articles_fetched = len(new_raw)

        if new_raw:
            new_scored = summarize_articles(new_raw, theme["hashtag"])
            # Merge into pool (update_pool handles prune + sort by relevance)
            articles = theme_cache.update_pool(theme_type, theme_id, new_scored)
        elif pool:
            articles = pool  # nothing new this run, deliver from existing pool
        else:
            status = "no_articles"
            logger.warning("no_articles: theme=%s/%d name=%s", theme_type, theme_id, theme_name)
            try:
                db.execute_many([(
                    "INSERT INTO delivery_errors (theme_id, theme_type, error_msg, occurred_at) VALUES (?, ?, ?, ?)",
                    [theme_id, theme_type, f"no_articles: RSS feeds returned nothing for '{theme_name}'", now_ts],
                )])
            except Exception:
                pass
            return _build_result(
                theme_type, theme_id, theme_name, user_count,
                status, articles_fetched, articles_sent, error_msg,
                theme_info, sent_articles, delivery_log_statements, posted_urls,
            )

        if not articles:
            status = "ai_empty"
            logger.warning("ai_empty: theme=%s/%d name=%s", theme_type, theme_id, theme_name)
            try:
                db.execute_many([(
                    "INSERT INTO delivery_errors (theme_id, theme_type, error_msg, occurred_at) VALUES (?, ?, ?, ?)",
                    [theme_id, theme_type, f"ai_empty: AI returned no summaries for '{theme_name}'", now_ts],
                )])
            except Exception:
                pass
            return _build_result(
                theme_type, theme_id, theme_name, user_count,
                status, articles_fetched, articles_sent, error_msg,
                theme_info, sent_articles, delivery_log_statements, posted_urls,
            )

        sent_articles = articles

        # Fan out to each user
        pool_urls = {a["url"] for a in articles}
        for user in users:
            # Per-user dedup: skip articles this user has ever received
            already_received = {
                row["article_url"]
                for row in db.execute(
                    "SELECT article_url FROM delivery_log "
                    "WHERE user_id = ? AND status = 'sent'",
                    [user["user_id"]],
                )
            }

            # Daily per-theme cap: if the user already received their quota for this
            # theme today (URLs overlap with the current pool), don't deliver more
            # even if new articles were added to the pool since their last delivery.
            received_today_from_theme = already_received & pool_urls
            if len(received_today_from_theme) >= user["effective_articles_per_theme"]:
                try:
                    send_already_received_note(
                        user["user_id"], theme_info["name"], theme_info["hashtag"]
                    )
                except Exception as e:
                    logger.warning("Failed to send already-received note to %d: %s", user["user_id"], e)
                continue

            # Dedup first, then slice — ensures user gets top-N fresh articles
            new_articles = [a for a in articles if a["url"] not in already_received]
            new_articles = new_articles[:user["effective_articles_per_theme"]]

            if not new_articles:
                try:
                    send_already_received_note(
                        user["user_id"], theme_info["name"], theme_info["hashtag"]
                    )
                except Exception as e:
                    logger.warning("Failed to send already-received note to %d: %s", user["user_id"], e)
                continue

            for article in new_articles:
                try:
                    post_article(user_id=user["user_id"], article=article)
                    posted_urls.append(article["url"])
                    articles_sent += 1
                    delivery_log_statements.append((
                        "INSERT INTO delivery_log (user_id, article_url, status, sent_at) VALUES (?, ?, ?, ?)",
                        [user["user_id"], article["url"], "sent", now_ts]
                    ))
                    time.sleep(0.1)  # avoid Telegram flood limits
                except Exception as e:
                    logger.error("Failed to post to user %d: %s", user["user_id"], e)
                    delivery_log_statements.append((
                        "INSERT INTO delivery_log (user_id, article_url, status, sent_at) VALUES (?, ?, ?, ?)",
                        [user["user_id"], article["url"], "failed", now_ts]
                    ))

        # Write delivery_log per-theme immediately so admin panel sees up-to-date counts
        # even if other themes are still processing in parallel.
        if delivery_log_statements:
            try:
                db.execute_many(delivery_log_statements)
                delivery_log_statements = []  # mark as flushed
            except Exception as e:
                logger.error("Failed to write delivery_log for theme %s/%d: %s", theme_type, theme_id, e)

    except Exception as e:
        status = "error"
        error_msg = str(e)
        logger.error("Unexpected error processing theme %s: %s", theme_name, e)
        try:
            db.execute_many([(
                "INSERT INTO delivery_errors (theme_id, theme_type, error_msg, occurred_at) VALUES (?, ?, ?, ?)",
                [theme_id, theme_type, str(e), now_ts]
            )])
        except Exception as db_err:
            logger.error("Failed to write delivery_error: %s", db_err)

    return _build_result(
        theme_type, theme_id, theme_name, user_count,
        status, articles_fetched, articles_sent, error_msg,
        theme_info, sent_articles, delivery_log_statements, posted_urls,
    )


def _build_result(
    theme_type, theme_id, theme_name, user_count,
    status, articles_fetched, articles_sent, error_msg,
    theme_info, sent_articles, delivery_log_statements, posted_urls,
) -> dict:
    # Emit structured per-theme log
    if error_msg:
        logger.info(
            "theme_id=%d theme_type=%s theme_name=%s user_count=%d "
            "articles_fetched=%d articles_sent=%d status=%s error=%s",
            theme_id, theme_type, theme_name, user_count,
            articles_fetched, articles_sent, status, error_msg,
        )
    else:
        logger.info(
            "theme_id=%d theme_type=%s theme_name=%s user_count=%d "
            "articles_fetched=%d articles_sent=%d status=%s",
            theme_id, theme_type, theme_name, user_count,
            articles_fetched, articles_sent, status,
        )
    return {
        "theme_type": theme_type,
        "theme_id": theme_id,
        "theme_name": theme_name,
        "user_count": user_count,
        "status": status,
        "articles_fetched": articles_fetched,
        "articles_sent": articles_sent,
        "error_msg": error_msg,
        "theme_info": theme_info,
        "sent_articles": sent_articles,
        "delivery_log_statements": delivery_log_statements,
        "posted_urls": posted_urls,
    }


def run():
    now_utc = datetime.now(timezone.utc)
    run_start = time.monotonic()
    hour_utc = now_utc.hour
    weekday = now_utc.isoweekday()  # 1=Mon...7=Sun

    logger.info("run start: hour=%d weekday=%d", hour_utc, weekday)

    # Step 1: find users due this hour
    deliveries = get_due_deliveries(hour_utc=hour_utc, weekday=weekday)
    if not deliveries:
        logger.info("No users due this hour")
        check_expiry_reminders()
        duration = time.monotonic() - run_start
        logger.info("run complete: themes=0 users=0 articles_sent=0 errors=0 duration=%.1fs", duration)
        return

    # Step 2: group by theme
    groups = group_by_theme(deliveries)
    logger.info("%d unique theme(s) to process for %d delivery row(s)", len(groups), len(deliveries))

    now_ts = int(time.time())

    # Step 3: process all themes in parallel
    futures_map = {}
    with ThreadPoolExecutor(max_workers=_MAX_THEME_WORKERS) as executor:
        for (theme_type, theme_id), users in groups.items():
            future = executor.submit(
                _process_theme,
                theme_type, theme_id, users,
                now_ts,
            )
            futures_map[future] = (theme_type, theme_id)

    results = []
    for future in as_completed(futures_map):
        try:
            results.append(future.result())
        except Exception as e:
            theme_type, theme_id = futures_map[future]
            logger.error("Unhandled exception in theme worker (%s, %d): %s", theme_type, theme_id, e)

    # Step 4: aggregate and write to DB
    total_themes = len(results)
    total_users_served = sum(r["user_count"] for r in results)
    total_articles_sent = sum(r["articles_sent"] for r in results)
    total_errors = sum(1 for r in results if r["status"] == "error")

    all_posted_urls: list[str] = []
    all_delivery_logs: list[tuple] = []
    for r in results:
        all_posted_urls.extend(r["posted_urls"])
        all_delivery_logs.extend(r["delivery_log_statements"])

    # Mark URLs as posted (global dedup)
    if all_posted_urls:
        statements = [
            ("INSERT OR IGNORE INTO posted_articles (url, posted_at) VALUES (?, ?)", [url, now_ts])
            for url in set(all_posted_urls)
        ]
        db.execute_many(statements)

    # Batch insert delivery_log
    if all_delivery_logs:
        try:
            db.execute_many(all_delivery_logs)
        except Exception as e:
            logger.error("Failed to write delivery_log: %s", e)

    # Step 5: digest history for monthly users (batch per group)
    for r in results:
        theme = r["theme_info"]
        articles = r["sent_articles"]
        if not theme or not articles:
            continue

        theme_type = r["theme_type"]
        theme_id = r["theme_id"]
        users = groups[(theme_type, theme_id)]

        digest_statements = []
        for user in users:
            if user.get("effective_tier") != "monthly":
                continue
            user_articles = articles[:user["effective_articles_per_theme"]]
            digest_statements.append((
                "INSERT INTO digest_history "
                "(user_id, theme_type, theme_id, theme_name, articles, sent_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [user["user_id"], theme_type, theme_id,
                 theme["name"], json.dumps(user_articles), now_ts],
            ))

        if digest_statements:
            try:
                db.execute_many(digest_statements)
            except Exception as e:
                logger.error("Failed to write digest history for theme (%s, %d): %s", theme_type, theme_id, e)

    # Step 6: expiry reminders
    check_expiry_reminders()
    duration = time.monotonic() - run_start
    logger.info(
        "run complete: themes=%d users=%d articles_sent=%d errors=%d duration=%.1fs",
        total_themes, total_users_served, total_articles_sent, total_errors, duration,
    )


if __name__ == "__main__":
    run()
