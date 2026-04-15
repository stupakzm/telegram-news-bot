import json
import time
import db.client as db

POOL_TTL = 36 * 3600  # articles older than this are pruned from the pool (36h avoids midnight boundary issues)


def get_pool(theme_type: str, theme_id: int) -> list[dict]:
    """
    Return the current article pool for a theme, pruned of entries older than POOL_TTL.
    Returns empty list if no pool exists yet.
    """
    rows = db.execute(
        "SELECT articles FROM theme_article_pool WHERE theme_type = ? AND theme_id = ?",
        [theme_type, theme_id],
    )
    if not rows:
        return []
    cutoff = int(time.time()) - POOL_TTL
    articles = json.loads(rows[0]["articles"])
    return [a for a in articles if a.get("fetched_at", 0) > cutoff]


def update_pool(theme_type: str, theme_id: int, new_articles: list[dict]) -> list[dict]:
    """
    Merge new_articles into the existing pool:
    - Stamps each new article with fetched_at = now
    - Deduplicates by URL (existing pool entries preserved as-is)
    - Prunes entries older than POOL_TTL
    - Sorts by relevance desc
    - Persists and returns the updated pool
    """
    now = int(time.time())
    existing = get_pool(theme_type, theme_id)  # already pruned
    existing_urls = {a["url"] for a in existing}

    for article in new_articles:
        if article["url"] not in existing_urls:
            article["fetched_at"] = now
            existing.append(article)
            existing_urls.add(article["url"])

    pool = sorted(existing, key=lambda a: a.get("relevance", 0), reverse=True)

    db.execute_many([(
        "INSERT OR REPLACE INTO theme_article_pool "
        "(theme_type, theme_id, articles, updated_at) VALUES (?, ?, ?, ?)",
        [theme_type, theme_id, json.dumps(pool), now],
    )])

    return pool
