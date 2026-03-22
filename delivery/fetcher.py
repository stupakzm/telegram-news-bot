import logging
logger = logging.getLogger(__name__)
import feedparser
import db.client as db
from bot.validation import validate_rss_url


def fetch_articles(theme: dict) -> list[dict]:
    """
    Fetch new articles for a theme (default or custom).
    Filters out URLs already in posted_articles.
    Returns list of article dicts.

    theme dict keys: id, theme_type, name, hashtag, rss_feeds (list of URLs)
    """
    import time as _time
    cutoff = int(_time.time()) - 24 * 3600
    posted = {row["url"] for row in db.execute(
        "SELECT url FROM posted_articles WHERE posted_at > ?", [cutoff]
    )}
    articles = []

    for feed_url in theme["rss_feeds"]:
        if not validate_rss_url(feed_url):
            logger.warning("Skipping restricted RSS URL: %s", feed_url)
            continue
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = getattr(entry, "link", None)
                if not url or url in posted:
                    continue
                articles.append({
                    "url": url,
                    "title": getattr(entry, "title", ""),
                    "description": getattr(entry, "summary", ""),
                    "theme_type": theme["theme_type"],
                    "theme_id": theme["id"],
                    "hashtag": theme["hashtag"],
                })
        except Exception as e:
            logger.warning("RSS feed failed: url=%s error=%s", feed_url, e)
            continue

    return articles
