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
        return

    # Step 2: group by theme
    groups = group_by_theme(deliveries)
    logger.info("%d unique theme(s) to process for %d delivery row(s)", len(groups), len(deliveries))

    all_posted_urls: list[str] = []
    # track actual articles sent per group for digest history
    group_theme_info: dict[tuple, dict] = {}
    group_sent_articles: dict[tuple, list[dict]] = {}

    now_ts = int(time.time())
    cutoff_ts = now_ts - 24 * 3600  # only check recently posted URLs for dedup

    for (theme_type, theme_id), users in groups.items():
        theme = get_theme_info(theme_type, theme_id)
        if not theme:
            logger.warning("Theme not found: theme_type=%s theme_id=%d", theme_type, theme_id)
            continue

        group_theme_info[(theme_type, theme_id)] = theme

        # Step 3: cache check
        articles = theme_cache.get_cached(theme_type, theme_id, date_str, quarter)

        if articles is None:
            # Cache miss: fetch + summarize
            try:
                raw_articles = fetch_articles(theme)
                if not raw_articles:
                    logger.info("No new articles for %s", theme["name"])
                    continue
                articles = summarize_articles(raw_articles, theme["hashtag"])
                if not articles:
                    logger.info("AI returned no summaries for %s", theme["name"])
                    continue
            except Exception as e:
                logger.error("Error fetching/summarizing %s: %s", theme["name"], e)
                continue
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

        # Step 4: fan out to each user
        # Collect the canonical sent list for this group (same for all users, sliced per-user)
        group_sent_articles[(theme_type, theme_id)] = articles

        for user in users:
            user_articles = articles[:user["effective_articles_per_theme"]]
            for article in user_articles:
                try:
                    post_article(user_id=user["user_id"], article=article)
                    all_posted_urls.append(article["url"])
                    time.sleep(0.1)  # avoid Telegram flood limits
                except Exception as e:
                    logger.error("Failed to post to user %d: %s", user["user_id"], e)

    # Step 5: mark URLs as posted (global dedup)
    if all_posted_urls:
        statements = [
            ("INSERT OR IGNORE INTO posted_articles (url, posted_at) VALUES (?, ?)", [url, now_ts])
            for url in set(all_posted_urls)
        ]
        db.execute_many(statements)

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
    logger.info("Delivery run complete")


if __name__ == "__main__":
    run()
