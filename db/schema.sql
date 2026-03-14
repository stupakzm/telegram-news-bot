CREATE TABLE IF NOT EXISTS users (
    user_id          INTEGER PRIMARY KEY,
    tier             TEXT    NOT NULL DEFAULT 'free',  -- 'free' | 'one_time' | 'monthly'
    tier_expires_at  INTEGER,                           -- NULL for free/one_time; Unix ts for monthly
    created_at       INTEGER NOT NULL,
    stars_paid       INTEGER NOT NULL DEFAULT 0,
    last_reminder_at INTEGER                            -- Unix ts of last expiry reminder; NULL if never
);

CREATE TABLE IF NOT EXISTS themes (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT    NOT NULL,
    hashtag   TEXT    NOT NULL,
    rss_feeds TEXT    NOT NULL,  -- JSON array of URL strings
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS custom_themes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(user_id),
    name         TEXT    NOT NULL,
    hashtag      TEXT    NOT NULL,  -- e.g. '#evs', used in AI prompt and post formatting
    rss_feeds    TEXT    NOT NULL,  -- JSON array of URL strings
    ai_suggested INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS user_themes (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id            INTEGER NOT NULL REFERENCES users(user_id),
    theme_type         TEXT    NOT NULL,  -- 'default' | 'custom'
    theme_id           INTEGER NOT NULL,  -- references themes.id or custom_themes.id
    articles_per_theme INTEGER NOT NULL DEFAULT 1  -- count of news items (not posts): 1 free/one_time, 1-2 monthly
);

CREATE TABLE IF NOT EXISTS user_schedules (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(user_id),
    user_theme_id INTEGER REFERENCES user_themes(id),  -- NULL = global schedule (free tier)
    days          TEXT    NOT NULL,                     -- JSON array e.g. [1,3,5] (1=Mon...7=Sun)
    hour_utc      INTEGER NOT NULL,                     -- 0-23
    UNIQUE (user_id, user_theme_id)
);

CREATE TABLE IF NOT EXISTS digest_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(user_id),
    theme_type TEXT    NOT NULL,
    theme_id   INTEGER NOT NULL,
    theme_name TEXT    NOT NULL,  -- snapshot at send time
    articles   TEXT    NOT NULL,  -- JSON array of article summaries
    sent_at    INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_digest_history_user_date
    ON digest_history(user_id, sent_at DESC);

CREATE TABLE IF NOT EXISTS posted_articles (
    url       TEXT    PRIMARY KEY,
    posted_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS theme_cache (
    theme_type   TEXT    NOT NULL,
    theme_id     INTEGER NOT NULL,
    cache_date   TEXT    NOT NULL,  -- 'YYYY-MM-DD' UTC
    quarter      INTEGER NOT NULL,  -- 0-3 (hour // 6)
    articles     TEXT    NOT NULL,  -- JSON array of AI summaries
    generated_at INTEGER NOT NULL,
    PRIMARY KEY (theme_type, theme_id, cache_date, quarter)
);

CREATE TABLE IF NOT EXISTS user_pending_actions (
    user_id    INTEGER PRIMARY KEY REFERENCES users(user_id),
    action     TEXT    NOT NULL,  -- e.g. 'addtheme_ai_topic' | 'addtheme_ai_name' | 'addtheme_manual_name'
    data       TEXT,              -- JSON blob of intermediate state (e.g. selected feed URLs)
    created_at INTEGER NOT NULL
);
