# Structure

**Analysis Date:** 2026-03-21

## Directory Layout

```
telegram-news-bot/
├── api/                    # Vercel serverless entry point
│   ├── __init__.py
│   └── webhook.py          # HTTP handler — receives Telegram updates
│
├── bot/                    # Bot logic layer
│   ├── __init__.py
│   ├── router.py           # Update routing (commands, callbacks, pending actions)
│   ├── telegram.py         # Telegram API HTTP wrapper
│   └── commands/           # One module per bot command
│       ├── __init__.py
│       ├── addtheme.py     # /addtheme (AI-suggested) + /addthememanual
│       ├── history.py      # /history
│       ├── payments.py     # /upgrade payment flow, invoice handling
│       ├── schedule.py     # /schedule — day/time picker
│       ├── settings.py     # /settings overview
│       ├── start.py        # /start — onboarding
│       ├── themes.py       # /themes — browse/add/remove themes
│       └── upgrade.py      # /upgrade — tier upsell UI
│
├── db/                     # Database layer
│   ├── __init__.py
│   ├── client.py           # Turso HTTP client (execute, execute_many)
│   ├── init_db.py          # DB initialization script
│   ├── schema.sql          # 8-table schema definition
│   └── seed_themes.py      # Default themes seed data
│
├── delivery/               # News delivery pipeline
│   ├── __init__.py
│   ├── main.py             # Orchestrator — called by GitHub Actions hourly
│   ├── scheduler.py        # Query due deliveries, expiry reminders
│   ├── cache.py            # Quarter-based article cache (6h windows)
│   ├── fetcher.py          # RSS feed fetcher + dedup filter
│   ├── ai.py               # AI summarization (Gemini → Groq fallback)
│   └── poster.py           # Send articles to Telegram users
│
├── themes/                 # Default theme definitions
│   ├── __init__.py
│   └── default_themes.json # Seed data for built-in themes
│
├── tests/                  # Test suite
│   ├── __init__.py
│   ├── bot/                # Command-level tests
│   │   ├── test_addtheme.py
│   │   ├── test_history.py
│   │   ├── test_payments.py
│   │   ├── test_router.py
│   │   ├── test_schedule.py
│   │   ├── test_settings.py
│   │   ├── test_start.py
│   │   └── test_themes.py
│   ├── test_ai.py
│   ├── test_cache.py
│   ├── test_db_client.py
│   ├── test_fetcher.py
│   ├── test_poster.py
│   └── test_scheduler.py
│
├── docs/                   # Documentation
│   ├── deployment.md
│   └── superpowers/        # Feature specs and plans
│
├── .github/
│   └── workflows/
│       └── deliver.yml     # Hourly GitHub Actions cron for delivery
│
├── .env.example            # Required environment variables
├── requirements.txt        # Production dependencies
├── requirements-dev.txt    # Dev/test dependencies
├── vercel.json             # Vercel deployment config
└── .gitignore
```

## Key Locations

| What | Where |
|------|-------|
| Webhook entry point | `api/webhook.py` |
| Command routing | `bot/router.py` → `COMMAND_MAP` |
| Add new command | `bot/commands/<name>.py` + register in `bot/router.py` |
| Database schema | `db/schema.sql` |
| DB queries | `db/client.py` — `execute()` / `execute_many()` |
| Delivery orchestrator | `delivery/main.py:run()` |
| AI summarization | `delivery/ai.py:summarize_articles()` |
| Article cache | `delivery/cache.py` |
| Default themes data | `themes/default_themes.json` |
| GitHub Actions cron | `.github/workflows/deliver.yml` |
| Env var reference | `.env.example` |

## Naming Conventions

- **Modules:** lowercase snake_case (`addtheme.py`, `db_client.py`)
- **Command handlers:** `handle(message: dict)` as primary entry, additional helpers named by action (`toggle_feed`, `feeds_done`, `handle_pending`)
- **DB functions:** `execute(sql, args)` for single, `execute_many(statements)` for batch
- **Delivery functions:** named by stage (`fetch_articles`, `summarize_articles`, `post_article`, `get_due_deliveries`)
- **Test files:** `test_<module>.py` mirroring source structure

---
*Structure analysis: 2026-03-21*
