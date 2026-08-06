CREATE TABLE IF NOT EXISTS users (
    user_id          INTEGER PRIMARY KEY,
    tier             TEXT    NOT NULL DEFAULT 'expired',  -- 'trial' | 'vip' | 'svip' | 'expired'
    tier_expires_at  INTEGER,                              -- Unix ts; NULL if no active plan
    timezone         TEXT,                                 -- IANA tz, e.g. 'Europe/Kyiv'; NULL = UTC
    trial_used       INTEGER NOT NULL DEFAULT 0,           -- 0|1, prevents re-trial after expiry
    stars_paid       INTEGER NOT NULL DEFAULT 0,
    last_reminder_at INTEGER,
    created_at       INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS user_feeds (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL REFERENCES users(user_id),
    url      TEXT    NOT NULL,
    added_at INTEGER NOT NULL,
    UNIQUE (user_id, url)
);

CREATE INDEX IF NOT EXISTS idx_user_feeds_user
    ON user_feeds(user_id);

CREATE TABLE IF NOT EXISTS user_keywords (
    user_id    INTEGER NOT NULL REFERENCES users(user_id),
    keyword    TEXT    NOT NULL,           -- stored as entered; matched case-insensitive
    added_at   INTEGER NOT NULL,
    PRIMARY KEY (user_id, keyword)
);

CREATE TABLE IF NOT EXISTS seen_articles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(user_id),
    feed_url        TEXT    NOT NULL,
    article_url     TEXT    NOT NULL,
    article_title   TEXT    NOT NULL,
    article_body    TEXT    NOT NULL,      -- raw text, capped ~8KB by writer
    score           INTEGER NOT NULL,      -- total keyword occurrences across title+body
    match_breakdown TEXT    NOT NULL,      -- JSON object: {"Tesla":12,"Autopilot":8}
    fetched_at      INTEGER NOT NULL,
    published_at    INTEGER NOT NULL DEFAULT 0,  -- from the feed; 0 if undated
    sent_at         INTEGER,               -- NULL until delivered to user
    UNIQUE (user_id, article_url)
);

CREATE INDEX IF NOT EXISTS idx_seen_articles_user_unsent
    ON seen_articles(user_id, sent_at, score DESC);

CREATE TABLE IF NOT EXISTS delivery_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(user_id),
    article_url TEXT    NOT NULL,
    status      TEXT    NOT NULL,          -- 'sent' | 'failed'
    sent_at     INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_delivery_log_user_time
    ON delivery_log(user_id, sent_at DESC);

CREATE TABLE IF NOT EXISTS delivery_errors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,                   -- NULL for global errors
    feed_url    TEXT,
    error_msg   TEXT    NOT NULL,
    occurred_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_delivery_errors_time
    ON delivery_errors(occurred_at DESC);

CREATE TABLE IF NOT EXISTS url_packs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT    NOT NULL UNIQUE,
    urls      TEXT    NOT NULL,            -- JSON array of URL strings
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS user_pending_actions (
    user_id    INTEGER PRIMARY KEY REFERENCES users(user_id),
    action     TEXT    NOT NULL,
    data       TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(user_id),
    message_id INTEGER NOT NULL,
    sent_at    INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bot_messages_user
    ON bot_messages(user_id);

CREATE TABLE IF NOT EXISTS article_reactions (
    user_id     INTEGER NOT NULL REFERENCES users(user_id),
    article_url TEXT    NOT NULL,
    reaction    TEXT    NOT NULL,
    reacted_at  INTEGER NOT NULL,
    PRIMARY KEY (user_id, article_url)
);

CREATE INDEX IF NOT EXISTS idx_article_reactions_reaction
    ON article_reactions(reaction);

CREATE TABLE IF NOT EXISTS rate_limit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    occurred_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rate_limit_log_user_time
    ON rate_limit_log(user_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS run_state (
    key        TEXT    PRIMARY KEY,        -- 'last_successful_run'
    value      INTEGER NOT NULL,           -- Unix ts of the hour slot covered
    updated_at INTEGER NOT NULL
);
