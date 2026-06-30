#!/usr/bin/env python3
"""
Seed the url_packs table from themes/url_packs.json.

Usage: python db/seed_url_packs.py
"""
import json
import os
import sys

from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db.client import execute_many


def main() -> None:
    with open("themes/url_packs.json") as f:
        packs = json.load(f)

    statements = [
        (
            "INSERT OR REPLACE INTO url_packs (name, urls, is_active) VALUES (?, ?, 1)",
            [p["name"], json.dumps(p["urls"])],
        )
        for p in packs
    ]
    execute_many(statements)
    print(f"Seeded {len(packs)} url packs.")


if __name__ == "__main__":
    main()
