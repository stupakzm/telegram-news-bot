# main.py
import os
import random
from dotenv import load_dotenv

from config import RSS_FEEDS, POSTS_PER_RUN_MIN, POSTS_PER_RUN_MAX, POSTED_IDS_FILE
from fetcher import fetch_all_articles, load_posted_ids, save_posted_ids
from ai import summarize_articles
from poster import post_article


def select_articles(articles: list) -> list:
    """Pick 3-10 articles, balanced across categories."""
    by_category = {}
    for a in articles:
        by_category.setdefault(a["category"], []).append(a)

    selected = []
    # round-robin across categories
    while len(selected) < POSTS_PER_RUN_MAX and any(by_category.values()):
        for cat in list(by_category.keys()):
            if by_category[cat] and len(selected) < POSTS_PER_RUN_MAX:
                selected.append(by_category[cat].pop(0))

    return selected[:random.randint(POSTS_PER_RUN_MIN, POSTS_PER_RUN_MAX)]


def run(gemini_key: str, groq_key: str, bot_token: str, channel_id: str):
    print("[main] Loading posted IDs...")
    posted_ids = load_posted_ids(POSTED_IDS_FILE)
    print(f"[main] {len(posted_ids)} previously posted articles.")

    print("[main] Fetching RSS feeds...")
    articles = fetch_all_articles(RSS_FEEDS, posted_ids)
    print(f"[main] Found {len(articles)} new articles.")

    if not articles:
        print("[main] No new articles. Exiting.")
        return

    selected = select_articles(articles)
    print(f"[main] Selected {len(selected)} articles to post.")

    print("[main] Summarizing with AI...")
    summaries = summarize_articles(selected, gemini_key, groq_key)

    new_ids = set()
    for summary in summaries:
        try:
            print(f"[main] Posting: {summary['title']}")
            post_article(summary, bot_token, channel_id)
            new_ids.add(summary["id"])
        except Exception as e:
            print(f"[main] Failed to post {summary.get('id')}: {e}")

    updated_ids = posted_ids | new_ids
    save_posted_ids(POSTED_IDS_FILE, updated_ids)
    print(f"[main] Done. Posted {len(new_ids)} articles.")


if __name__ == "__main__":
    load_dotenv()
    run(
        gemini_key=os.environ["GEMINI_API_KEY"],
        groq_key=os.environ["GROQ_API_KEY"],
        bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
        channel_id=os.environ["TELEGRAM_CHANNEL_ID"],
    )
