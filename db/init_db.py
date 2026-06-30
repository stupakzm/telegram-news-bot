#!/usr/bin/env python3
"""
Initialize the database schema. Drops all old tables and recreates from schema.sql.

WARNING: destructive — wipes all user data. Run once during the keyword-rework migration.

Usage: python db/init_db.py
"""
import os
import sys

from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db.client import execute_many

_OLD_TABLES = [
    "themes",
    "custom_themes",
    "user_themes",
    "user_schedules",
    "digest_history",
    "theme_cache",
    "theme_article_pool",
    "posted_articles",
]

_NEW_TABLES = [
    "users",
    "user_feeds",
    "user_keywords",
    "seen_articles",
    "delivery_log",
    "delivery_errors",
    "url_packs",
    "user_pending_actions",
    "bot_messages",
    "article_reactions",
]


def main() -> None:
    drop_statements = [
        (f"DROP TABLE IF EXISTS {t}", [])
        for t in _OLD_TABLES + _NEW_TABLES
    ]
    execute_many(drop_statements)

    with open("db/schema.sql") as f:
        raw = f.read()

    # Strip inline `-- comments` before splitting (comments may contain `;`)
    stripped = "\n".join(line.split("--")[0] for line in raw.splitlines())
    statements = [(s.strip(), []) for s in stripped.split(";") if s.strip()]
    execute_many(statements)
    print(f"Schema applied: dropped {len(_OLD_TABLES + _NEW_TABLES)} tables, created {len(_NEW_TABLES)}.")


if __name__ == "__main__":
    main()
