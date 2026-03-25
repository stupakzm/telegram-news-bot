# delivery/main.py
"""
Main delivery orchestrator. Called by GitHub Actions every hour.
Usage: python -m delivery.main
"""
import json
import logging
import time
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
from delivery.poster import post_article


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


def run():
    now_utc = datetime.now(timezone.utc)
    run_start = time.monotonic()
    hour_utc = now_utc.hour
    weekday = now_utc.isoweekday()  # 1=Mon...7=Sun
    date_str = now_utc.strftime("%Y-%m-%d")
    quarter = theme_cache.current_quarter(hour_utc)

    logger.info("run start: date=%s quarter=Q%d hour=%d weekday=%d", date_str, quarter, hour_utc, weekday)

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

    total_themes = 0
    total_users_served = 0
    total_articles_sent = 0
    total_errors = 0

    all_posted_urls: list[str] = []
    # track actual articles sent per group for digest history
    group_theme_info: dict[tuple, dict] = {}
    group_sent_articles: dict[tuple, list[dict]] = {}

    now_ts = int(time.time())
    cutoff_ts = now_ts - 24 * 3600  # only check recently posted URLs for dedup
    delivery_log_statements: list[tuple] = []

    for (theme_type, theme_id), users in groups.items():
        status = "ok"
        articles_fetched = 0
        articles_sent = 0
        error_msg = None
        theme_name = "unknown"
        user_count = len(users)

        try:
            theme = get_theme_info(theme_type, theme_id)
            if not theme:
                status = "error"
                error_msg = "theme not found"
                logger.warning("Theme not found: theme_type=%s theme_id=%d", theme_type, theme_id)
                continue  # finally will emit structured log

            theme_name = theme["name"]
            group_theme_info[(theme_type, theme_id)] = theme

            # Step 3: cache check
            articles = theme_cache.get_cached(theme_type, theme_id, date_str, quarter)

            if articles is None:
                # Cache miss: fetch + summarize
                raw_articles = fetch_articles(theme)
                if not raw_articles:
                    status = "no_articles"
                    continue  # finally will emit structured log
                articles_fetched = len(raw_articles)
                articles = summarize_articles(raw_articles, theme["hashtag"])
                if not articles:
                    status = "ai_empty"
                    continue  # finally will emit structured log
                # Cache the result
                theme_cache.set_cache(theme_type, theme_id, date_str, quarter, articles)
            else:
                # Cache hit: re-filter against recent posted_articles
                posted = {
                    row["url"]
                    for row in db.execute(
                        "SELECT url FROM posted_articles WHERE posted_at > ?", [cutoff_ts]
                    )
                }
                articles = [a for a in articles if a["url"] not in posted]
                articles_fetched = len(articles)

            # Step 4: fan out to each user
            # Collect the canonical sent list for this group (same for all users, sliced per-user)
            group_sent_articles[(theme_type, theme_id)] = articles

            for user in users:
                user_articles = articles[:user["effective_articles_per_theme"]]
                for article in user_articles:
                    try:
                        post_article(user_id=user["user_id"], article=article)
                        all_posted_urls.append(article["url"])
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
        finally:
            # Per-theme structured log entry (D-07)
            if status == "error":
                logger.info(
                    "theme_id=%d theme_type=%s theme_name=%s user_count=%d "
                    "articles_fetched=%d articles_sent=%d status=%s error=%s",
                    theme_id, theme_type, theme_name, user_count,
                    articles_fetched, articles_sent, status, error_msg
                )
            else:
                logger.info(
                    "theme_id=%d theme_type=%s theme_name=%s user_count=%d "
                    "articles_fetched=%d articles_sent=%d status=%s",
                    theme_id, theme_type, theme_name, user_count,
                    articles_fetched, articles_sent, status
                )
            # Run-level counters (D-08)
            total_themes += 1
            if status == "error":
                total_errors += 1
            total_articles_sent += articles_sent
            total_users_served += user_count

    # Step 5: mark URLs as posted (global dedup)
    if all_posted_urls:
        statements = [
            ("INSERT OR IGNORE INTO posted_articles (url, posted_at) VALUES (?, ?)", [url, now_ts])
            for url in set(all_posted_urls)
        ]
        db.execute_many(statements)

    # Step 5b: batch insert delivery_log
    if delivery_log_statements:
        try:
            db.execute_many(delivery_log_statements)
        except Exception as e:
            logger.error("Failed to write delivery_log: %s", e)

    # Step 6: digest history for monthly users (batch per group)
    for (theme_type, theme_id), users in groups.items():
        theme = group_theme_info.get((theme_type, theme_id))
        articles = group_sent_articles.get((theme_type, theme_id))
        if not theme or not articles:
            continue

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

    # Step 7: expiry reminders
    check_expiry_reminders()
    duration = time.monotonic() - run_start
    logger.info(
        "run complete: themes=%d users=%d articles_sent=%d errors=%d duration=%.1fs",
        total_themes, total_users_served, total_articles_sent, total_errors, duration
    )


if __name__ == "__main__":
    run()
