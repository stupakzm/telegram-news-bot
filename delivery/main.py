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
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

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
from delivery.extract import fetch_article_text, feed_ships_stubs
from delivery.fetcher import fetch_today_articles
from delivery.scoring import score_article, format_relevance
from delivery.ai import summarize_articles
from delivery.poster import post_article
from delivery.personalize import (
    feed_reaction_bias,
    select_with_bias,
    REACTION_WINDOW_SECONDS,
)

# Concurrency defaults (overridable via env — see _max_user_workers).
# Send pacing is handled globally by delivery.poster's token bucket, not by a
# per-thread sleep, so many workers can't collectively exceed Telegram's rate.
_MAX_USER_WORKERS = 5          # concurrent users; env DELIVERY_MAX_WORKERS
_FEED_FETCH_WORKERS = 4        # concurrent feed fetches per user; env DELIVERY_FEED_WORKERS

# Cap on scraped article text used for scoring. Never stored, never sent to the
# AI — it only ever feeds the keyword matcher.
_MAX_SCORING_CHARS = 20000

# How many random fresh articles to send a user who has feeds but no keywords.
_RANDOM_SAMPLE_SIZE = 3
# Sentinel article_url marking a "nothing matched" note in delivery_log, used to
# rate-limit the quiet-day note to once per user per local day.
_QUIET_SENTINEL = "__quiet__"


def _notify(user_id: int, text: str) -> None:
    """Send a plain-text (no Markdown) system message to a user."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",
            json={"chat_id": user_id, "text": text, "disable_web_page_preview": True},
            timeout=10,
        )
    except Exception as e:
        logger.warning("notify failed user=%d: %s", user_id, e)

# Jaccard word-overlap threshold for near-duplicate titles across feeds.
_TITLE_SIMILARITY_THRESHOLD = 0.6
_TITLE_STOP_WORDS = {
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or",
    "is", "are", "was", "were", "it",
}


def _title_words(title: str) -> set[str]:
    words = re.sub(r"[^\w\s]", "", title.lower()).split()
    return {w for w in words if w not in _TITLE_STOP_WORDS and len(w) > 1}


def _titles_similar(w1: set[str], w2: set[str]) -> bool:
    if not w1 or not w2:
        return False
    return len(w1 & w2) / len(w1 | w2) >= _TITLE_SIMILARITY_THRESHOLD


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


def _existing_seen_urls_and_titles(user_id: int) -> tuple[set[str], list[set[str]]]:
    rows = db.execute(
        "SELECT article_url, article_title FROM seen_articles WHERE user_id = ?",
        [user_id],
    )
    urls = {r["article_url"] for r in rows}
    title_word_sets = [_title_words(r["article_title"]) for r in rows]
    return urls, title_word_sets


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except (ValueError, TypeError):
        return default


def _max_user_workers() -> int:
    return _env_int("DELIVERY_MAX_WORKERS", _MAX_USER_WORKERS)


def _feed_fetch_workers() -> int:
    return _env_int("DELIVERY_FEED_WORKERS", _FEED_FETCH_WORKERS)


def _fetch_all(feeds: list[str], today_start_ts: int) -> dict[str, object]:
    """Fetch every feed concurrently (W5).

    Returns {feed_url: articles_list | Exception}. Fetching is I/O-bound and
    independent per feed, so it parallelizes safely; the CALLER still processes
    results sequentially in feed order to keep dedup/scoring deterministic.
    """
    workers = min(_feed_fetch_workers(), len(feeds)) or 1
    results: dict[str, object] = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fetch_today_articles, url, today_start_ts): url for url in feeds}
        for fut, url in futures.items():
            try:
                results[url] = fut.result()
            except Exception as e:  # captured per-feed; caller records to delivery_errors
                results[url] = e
    return results


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


def _maybe_quiet_note(user_id: int, today_start_ts: int, now_ts: int) -> None:
    """Send a 'nothing matched' note at most once per user per local day.

    Skipped if the user already received real articles today (they're not in a
    silent day) or already got a quiet note earlier today.
    """
    already = db.execute(
        "SELECT status FROM delivery_log "
        "WHERE user_id = ? AND sent_at >= ? AND status IN ('sent', 'quiet') LIMIT 1",
        [user_id, today_start_ts],
    )
    if already:
        return
    _notify(
        user_id,
        "📭 Nothing matched your keywords in this slot. I'll keep checking — "
        "tweak them anytime with /keywords.",
    )
    try:
        db.execute_many([(
            "INSERT INTO delivery_log (user_id, article_url, status, sent_at) "
            "VALUES (?, ?, 'quiet', ?)",
            [user_id, _QUIET_SENTINEL, now_ts],
        )])
    except Exception as e:
        logger.warning("Failed to record quiet note for %d: %s", user_id, e)


def _deliver_random_no_keywords(user: dict, now_utc: datetime, feeds: list[str]) -> dict:
    """Deliver a few random fresh articles to a user who has no keywords yet."""
    user_id = user["user_id"]
    tz = user["timezone"]
    now_ts = int(now_utc.timestamp())
    today_start_ts = user_today_start_utc_ts(tz, now_utc)

    recent_sent = _recent_sent_urls(user_id, now_ts - 24 * 3600)
    fetch_errors: list[tuple[str, str]] = []
    candidates: list[dict] = []
    seen: set[str] = set()

    fetched = _fetch_all(feeds, today_start_ts)
    for feed_url in feeds:
        result = fetched[feed_url]
        if isinstance(result, Exception):
            fetch_errors.append((feed_url, f"{type(result).__name__}: {result}"))
            continue
        for article in result:
            url = article["url"]
            if url in recent_sent or url in seen:
                continue
            seen.add(url)
            candidates.append(article)

    _write_feed_errors(user_id, fetch_errors, now_ts)

    if not candidates:
        logger.info("user=%d status=no_articles reason=no_keywords", user_id)
        return {"user_id": user_id, "status": "no_articles", "sent": 0, "failed": 0}

    picks = random.sample(candidates, min(_RANDOM_SAMPLE_SIZE, len(candidates)))
    summaries = summarize_articles(picks)
    summary_by_url = {s["url"]: s for s in summaries}

    sent = 0
    failed = 0
    update_stmts: list[tuple] = []

    for pick in picks:
        ai = summary_by_url.get(pick["url"])
        if not ai:
            continue
        article = {
            "url": pick["url"],
            "title": pick["title"],
            "summary": ai.get("summary", ""),
            "is_important": ai.get("is_important"),
            "importance_detail": ai.get("importance_detail", ""),
            "relevance": "",  # no keywords → no relevance line
        }
        try:
            post_article(user_id=user_id, article=article)
            sent += 1
            update_stmts.append((
                "INSERT INTO delivery_log (user_id, article_url, status, sent_at) "
                "VALUES (?, ?, 'sent', ?)",
                [user_id, pick["url"], now_ts],
            ))
        except Exception as e:
            failed += 1
            logger.error("post_article (random) failed user=%d url=%s err=%s", user_id, pick["url"], e)
            update_stmts.append((
                "INSERT INTO delivery_log (user_id, article_url, status, sent_at) "
                "VALUES (?, ?, 'failed', ?)",
                [user_id, pick["url"], now_ts],
            ))

    if update_stmts:
        try:
            db.execute_many(update_stmts)
        except Exception as e:
            logger.error("Failed to persist random delivery for %d: %s", user_id, e)

    if sent:
        _notify(
            user_id,
            "💡 These are random fresh picks from your feeds. Add keywords with "
            "/keywords and I'll filter for the articles that actually matter to you.",
        )

    logger.info("user=%d status=random_no_keywords sent=%d failed=%d", user_id, sent, failed)
    return {"user_id": user_id, "status": "ok", "sent": sent, "failed": failed}


def _deliver_user(user: dict, now_utc: datetime) -> dict:
    user_id = user["user_id"]
    tz = user["timezone"]
    now_ts = int(now_utc.timestamp())
    today_start_ts = user_today_start_utc_ts(tz, now_utc)

    feeds = _load_feeds(user_id)
    keywords = _load_keywords(user_id)
    if not feeds:
        logger.info("skip user=%d reason=no_feeds", user_id)
        return {"user_id": user_id, "status": "no_config", "sent": 0, "failed": 0}
    if not keywords:
        # Has feeds but no keywords: send random fresh picks so the bot feels
        # alive, then nudge them to add keywords for real relevance filtering.
        return _deliver_random_no_keywords(user, now_utc, feeds)

    recent_sent = _recent_sent_urls(user_id, now_ts - 24 * 3600)
    seen_urls, seen_title_words = _existing_seen_urls_and_titles(user_id)

    fetch_errors: list[tuple[str, str]] = []
    new_rows: list[tuple] = []

    fetched = _fetch_all(feeds, today_start_ts)
    for feed_url in feeds:
        result = fetched[feed_url]
        if isinstance(result, Exception):
            fetch_errors.append((feed_url, f"{type(result).__name__}: {result}"))
            continue

        stub_feed = feed_ships_stubs(feed_url)
        for article in result:
            url = article["url"]
            if url in recent_sent or url in seen_urls:
                continue
            title_words = _title_words(article["title"])
            if any(_titles_similar(title_words, prev) for prev in seen_title_words):
                continue
            body = article["body"]
            # Stub-body feeds (HN ships "Comments") would otherwise be scored on
            # their title alone. Score against the real article text, but keep
            # the short feed body for storage and the AI prompt so token spend
            # is unchanged.
            scoring_body = body
            if stub_feed:
                full = fetch_article_text(url, _MAX_SCORING_CHARS)
                if full:
                    scoring_body = full

            score, breakdown = score_article(article["title"], scoring_body, keywords)
            new_rows.append((
                "INSERT OR IGNORE INTO seen_articles "
                "(user_id, feed_url, article_url, article_title, article_body, "
                "score, match_breakdown, fetched_at, published_at, sent_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                [
                    user_id, feed_url, url, article["title"], article["body"],
                    score, json.dumps(breakdown), now_ts,
                    article.get("published_at") or 0,
                ],
            ))
            seen_urls.add(url)
            seen_title_words.append(title_words)

    if new_rows:
        try:
            db.execute_many(new_rows)
        except Exception as e:
            logger.error("Failed to insert seen_articles for %d: %s", user_id, e)

    pool = db.execute(
        "SELECT id, feed_url, article_url, article_title, article_body, score, match_breakdown "
        "FROM seen_articles "
        "WHERE user_id = ? AND sent_at IS NULL AND score > 0 "
        # Equal-scoring articles used to tie arbitrarily; prefer the fresher one.
        # published_at is 0 for undated entries, so those sort last within a tie.
        "ORDER BY score DESC, published_at DESC",
        [user_id],
    )

    by_feed: dict[str, list[dict]] = {}
    for row in pool:
        by_feed.setdefault(row["feed_url"], []).append(row)

    # DQ-01: reactions gently adjust each feed's per-run quota (keywords/score
    # remain the primary signal). No reactions -> default 2 per feed, feed order.
    bias = feed_reaction_bias(user_id, now_ts - REACTION_WINDOW_SECONDS)
    selected: list[dict] = select_with_bias(feeds, by_feed, bias)

    if not selected:
        _write_feed_errors(user_id, fetch_errors, now_ts)
        _maybe_quiet_note(user_id, today_start_ts, now_ts)
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
    workers = _max_user_workers()
    msgs_cap = os.environ.get("TELEGRAM_MAX_MSGS_PER_SEC", "25")
    logger.info(
        "run start hour_utc=%d workers=%d feed_workers=%d msgs_per_sec_cap=%s",
        now_utc.hour, workers, _feed_fetch_workers(), msgs_cap,
    )

    due = get_due_users(now_utc)
    if not due:
        logger.info("run skip: no users due this hour")
        check_expiry_reminders()
        cleanup_seen_articles()
        return

    logger.info("processing %d due user(s)", len(due))

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(lambda u: _deliver_safely(u, now_utc), due))

    sent_total = sum(r["sent"] for r in results)
    failed_total = sum(r["failed"] for r in results)
    errors_total = sum(1 for r in results if r["status"] == "error")
    duration = time.monotonic() - run_start
    logger.info(
        "run complete users=%d sent=%d failed=%d errors=%d duration=%.1fs "
        "workers=%d msgs_per_sec_cap=%s",
        len(due), sent_total, failed_total, errors_total, duration, workers, msgs_cap,
    )

    check_expiry_reminders()
    cleanup_seen_articles()


if __name__ == "__main__":
    run()
