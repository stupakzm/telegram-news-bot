#!/usr/bin/env python3
# db/seed_themes.py
"""Run once: python db/seed_themes.py"""
import json, os, sys
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db.client import execute_many

with open("themes/default_themes.json") as f:
    themes = json.load(f)

statements = [
    (
        "INSERT OR IGNORE INTO themes (name, hashtag, rss_feeds, is_active) VALUES (?, ?, ?, 1)",
        [t["name"], t["hashtag"], json.dumps(t["rss_feeds"])],
    )
    for t in themes
]
execute_many(statements)
print(f"Seeded {len(themes)} themes.")
