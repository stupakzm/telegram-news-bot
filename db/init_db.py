#!/usr/bin/env python3
# db/init_db.py
"""Run once to create schema: python db/init_db.py"""
import os, sys
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db.client import execute_many

with open("db/schema.sql") as f:
    raw = f.read()

# Split on semicolons, skip empty statements
statements = [(s.strip(), []) for s in raw.split(";") if s.strip()]
execute_many(statements)
print("Schema applied.")
