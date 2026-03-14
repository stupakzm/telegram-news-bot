"""
Main delivery orchestrator. Called by GitHub Actions every hour.
Usage: python -m delivery.main
"""
import json
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

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

    print(f"[deliver] {date_str} Q{quarter} hour={hour_utc} weekday={weekday}")

    # Step 1: find users due this hour
    deliveries = get_due_deliveries(hour_utc=hour_utc, weekday=weekday)
    if not deliveries:
        print("[deliver] No users due this hour.")
        check_expiry_reminders()
        return

    # Step 2: group by theme
    groups = group_by_theme(deliveries)
    print(f"[deliver] {len(groups)} unique theme(s) to process for {len(deliveries)} delivery row(s)")

    all_posted_urls: list[str] = []

    for (theme_type, theme_id), users in groups.items():
        theme = get_theme_info(theme_type, theme_id)
        if not theme:
            print(f"[deliver] Theme ({theme_type}, {theme_id}) not found — skipping")
            continue

        # Step 3: cache check
        articles = theme_cache.get_cached(theme_type, theme_id, date_str, quarter)

        if articles is None:
            # Cache miss: fetch + summarize
            raw_articles = fetch_articles(theme)
            if not raw_articles:
                print(f"[deliver] No new articles for {theme['name']}")
                continue
            articles = summarize_articles(raw_articles, theme["hashtag"])
            if not articles:
                print(f"[deliver] AI returned no summaries for {theme['name']}")
                continue
            # Cache the result
            theme_cache.set_cache(theme_type, theme_id, date_str, quarter, articles)
        else:
            # Cache hit: still filter against posted_articles
            posted = {row["url"] for row in db.execute("SELECT url FROM posted_articles")}
            articles = [a for a in articles if a["url"] not in posted]

        # Step 4: fan out to each user
        for user in users:
            user_articles = articles[:user["effective_articles_per_theme"]]
            for article in user_articles:
                try:
                    post_article(user_id=user["user_id"], article=article)
                    all_posted_urls.append(article["url"])
                    time.sleep(0.1)  # avoid Telegram flood limits
                except Exception as e:
                    print(f"[deliver] Failed to post to user {user['user_id']}: {e}")

    # Step 5: mark URLs as posted (global dedup) — must run before digest_history
    if all_posted_urls:
        now_ts = int(time.time())
        statements = [
            ("INSERT OR IGNORE INTO posted_articles (url, posted_at) VALUES (?, ?)", [url, now_ts])
            for url in set(all_posted_urls)
        ]
        db.execute_many(statements)

    # Step 6: digest history for monthly users
    for (theme_type, theme_id), users in groups.items():
        theme = get_theme_info(theme_type, theme_id)
        if not theme:
            continue
        cached = theme_cache.get_cached(theme_type, theme_id, date_str, quarter)
        if not cached:
            continue
        for user in users:
            if user.get("effective_tier") != "monthly":
                continue
            user_articles = cached[:user["effective_articles_per_theme"]]
            try:
                db.execute_many([
                    (
                        "INSERT INTO digest_history "
                        "(user_id, theme_type, theme_id, theme_name, articles, sent_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        [user["user_id"], theme_type, theme_id,
                         theme["name"], json.dumps(user_articles), int(time.time())],
                    )
                ])
            except Exception as e:
                print(f"[deliver] Failed to write history for user {user['user_id']}: {e}")

    # Step 7: expiry reminders
    check_expiry_reminders()
    print("[deliver] Done.")


if __name__ == "__main__":
    run()
