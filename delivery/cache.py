import json
import re
import time
import db.client as db

POOL_TTL = 36 * 3600  # articles older than this are pruned from the pool (36h avoids midnight boundary issues)
_TITLE_SIMILARITY_THRESHOLD = 0.7  # Jaccard word-overlap threshold for near-duplicate titles


def _title_words(title: str) -> set[str]:
    """Normalize a title to a set of significant words."""
    words = re.sub(r"[^\w\s]", "", title.lower()).split()
    # Strip common stop words that inflate similarity scores
    stop = {"the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or", "is", "are", "was", "were", "it"}
    return {w for w in words if w not in stop and len(w) > 1}


def _titles_similar(t1: str, t2: str) -> bool:
    """Return True if two titles are likely the same story (Jaccard >= threshold)."""
    w1 = _title_words(t1)
    w2 = _title_words(t2)
    if not w1 or not w2:
        return False
    intersection = len(w1 & w2)
    union = len(w1 | w2)
    return (intersection / union) >= _TITLE_SIMILARITY_THRESHOLD


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
    existing_titles = [a.get("title", "") for a in existing]

    for article in new_articles:
        if article["url"] in existing_urls:
            continue
        new_title = article.get("title", "")
        if any(_titles_similar(new_title, t) for t in existing_titles):
            continue
        article["fetched_at"] = now
        existing.append(article)
        existing_urls.add(article["url"])
        existing_titles.append(new_title)

    pool = sorted(existing, key=lambda a: a.get("relevance", 0), reverse=True)

    db.execute_many([(
        "INSERT OR REPLACE INTO theme_article_pool "
        "(theme_type, theme_id, articles, updated_at) VALUES (?, ?, ?, ?)",
        [theme_type, theme_id, json.dumps(pool), now],
    )])

    return pool
