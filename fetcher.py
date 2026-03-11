# fetcher.py
import json
import feedparser
from config import MAX_STORED_IDS


def load_posted_ids(filepath: str) -> set:
    try:
        with open(filepath, "r") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_posted_ids(filepath: str, ids: set, max_size: int = MAX_STORED_IDS):
    trimmed = list(ids)[-max_size:]
    with open(filepath, "w") as f:
        json.dump(trimmed, f, indent=2)


def fetch_articles(feed_urls: list, category: str, posted_ids: set) -> list:
    articles = []
    for url in feed_urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                link = getattr(entry, "link", None)
                if not link or link in posted_ids:
                    continue
                articles.append({
                    "url": link,
                    "title": getattr(entry, "title", "No title"),
                    "description": getattr(entry, "summary", ""),
                    "category": category,
                })
        except Exception:
            continue
    return articles


def fetch_all_articles(rss_feeds: dict, posted_ids: set) -> list:
    all_articles = []
    for category, urls in rss_feeds.items():
        all_articles.extend(fetch_articles(urls, category, posted_ids))
    return all_articles
