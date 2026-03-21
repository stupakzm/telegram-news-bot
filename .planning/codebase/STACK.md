# Technology Stack

**Analysis Date:** 2026-03-21

## Languages

**Primary:**
- Python 3.13 - Primary runtime, backend logic, bot handling, and data processing

**Secondary:**
- YAML - GitHub Actions workflow configuration
- SQL - Database schema for Turso queries

## Runtime

**Environment:**
- Python 3.13 (specified in GitHub Actions workflow)
- Python 3.12 (available in development environment)

**Package Manager:**
- pip - Python package management
- Lockfile: No `requirements.txt.lock` present (pinned versions used)

## Frameworks

**Core:**
- feedparser 6.0.11 - RSS feed parsing for article extraction
- requests 2.32.3 - HTTP client for API calls (Telegram, Turso, Groq, etc.)
- python-dotenv 1.0.1 - Environment variable management
- google-generativeai 0.8.3 - Google Gemini AI API client

**Testing:**
- pytest 8.3.4 - Test framework and runner
- pytest-mock 3.14.0 - Mocking and fixtures for tests

**Build/Dev:**
- GitHub Actions - CI/CD pipeline for hourly delivery scheduling

## Key Dependencies

**Critical:**
- google-generativeai 0.8.3 - AI summarization (primary AI provider)
- feedparser 6.0.11 - Parsing RSS feeds for news articles
- requests 2.32.3 - HTTP communication with external APIs

**Infrastructure:**
- python-dotenv 1.0.1 - Secrets and configuration management via environment variables

## Configuration

**Environment:**
- Loaded via `python-dotenv` from `.env` file at runtime
- Required env vars: `TURSO_URL`, `TURSO_TOKEN`, `TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `STARS_ONETIME_PRICE`, `STARS_MONTHLY_PRICE`
- Example configuration in `.env.example`
- Secrets managed via GitHub Actions secrets in workflow file

**Build:**
- `vercel.json` - Serverless function configuration for Vercel deployment
  - Single Python function: `api/webhook.py`
  - Runtime: Python 3.12
  - Route: `/webhook` → `api/webhook.py`

## Platform Requirements

**Development:**
- Python 3.12+ (local development)
- pip for dependency management
- Shell/bash environment for running scripts

**Production:**
- Vercel - Serverless function hosting for webhook endpoint
- GitHub Actions - Scheduled task execution (hourly cron jobs)
- Turso - SQLite database provider (HTTP API)

**Deployment:**
- Vercel serverless functions handle incoming Telegram webhook updates
- GitHub Actions scheduled workflow runs `delivery.main` module hourly for news digest delivery

---

*Stack analysis: 2026-03-21*
