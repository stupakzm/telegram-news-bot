---
status: awaiting_human_verify
trigger: "Multiple delivery pipeline issues: late delivery, missing theme articles, slow sequential processing, Turso DB timeouts."
created: 2026-04-05T00:00:00Z
updated: 2026-04-05T00:00:00Z
---

## Current Focus
<!-- OVERWRITE on each update - reflects NOW -->

hypothesis: All 5 issues have clear root causes now identified.
  1. TIMING: GitHub Actions cron is inherently late (5-27 min), and pip install on every run adds ~2 min. No pip caching.
  2. SEQUENTIAL: main.py iterates themes in a for loop with no async/parallel execution. 5 themes * ~80s each = 400s.
  3. AI_EMPTY (Privacy & Security): 70 articles sent to Gemini in one prompt exceeds token limits → JSON parse fail → 429 quota on retry → Groq 413 (payload too large). No article count cap before AI call.
  4. 400 Bad Request on sendMessage: format_post uses Markdown parse_mode but article title/summary from AI may contain unescaped Markdown special chars (*, _, [, ], etc.) → Telegram rejects malformed Markdown.
  5. TURSO TIMEOUT: Every DB call creates a new HTTP connection with timeout=10s. Turso HTTP endpoint has cold-start latency. No retry logic on timeout.
test: all evidence gathered from source code read
expecting: confirm all 5 root causes
next_action: implement fixes

## Symptoms
<!-- Written during gathering, then IMMUTABLE -->

expected:
- 5 themes delivered every day at exactly 11:00 UTC
- Each theme delivers 1 article per user per day
- Run completes quickly

actual:
- Delivery arrives 30-50 min late (13:30-13:50 local = 11:30-11:50 UTC instead of 11:00 UTC)
- Some themes deliver 0 articles (ai_empty or 400 Bad Request errors)
- Total run takes ~7 minutes (401.9s on 2026-04-05, 344.2s on 2026-04-02)
- Processing is sequential, one theme at a time

errors:
2026-04-05:
- theme_id=3 Privacy & Security: ai_empty (Gemini JSON parse error, Gemini 429 quota exceeded, Groq 413 payload too large)
- theme_id=4 Software Development: 400 Bad Request on sendMessage, articles_sent=0
- Run duration: 401.9s for 5 themes

2026-04-02:
- theme_id=4 Software Development: 400 Bad Request on sendMessage, articles_sent=0
- theme_id=2 Artificial Intelligence: Turso DB connection timeout (connect timeout=10s)
- Run duration: 344.2s for 5 themes

started: Ongoing. Schedule set to all 7 days at 11:00 UTC.
reproduction: Runs daily via GitHub Actions (or similar scheduler) at 11:00 UTC.

## Eliminated
<!-- APPEND only - prevents re-investigating -->

## Evidence
<!-- APPEND only - facts discovered -->

- timestamp: 2026-04-05T00:00:00Z
  checked: .github/workflows/deliver.yml
  found: cron is "0 * * * *" (every hour). No pip cache. pip install runs every time before delivery. Python setup + pip install typically takes 90-120s on GitHub Actions ubuntu-latest. This means the actual script starts at ~11:02-11:03 UTC at best, but GitHub itself schedules cron with up to 15-30 min queue delay under load.
  implication: The 27-minute delay on 2026-04-05 is inherent to GitHub Actions scheduling. pip install without caching adds ~2 min of avoidable overhead on top.

- timestamp: 2026-04-05T00:00:00Z
  checked: delivery/main.py lines 88-190
  found: Single for loop iterates (theme_type, theme_id) groups sequentially. Each iteration: fetch RSS feeds (network I/O), call AI API (network I/O, 20-60s), fan out posts to users (network I/O). No asyncio, no threading, no concurrent.futures.
  implication: With 5 themes and each taking 60-80s (AI call dominates), total is ~400s. This matches the observed 401.9s. Fix: run themes in parallel using asyncio or concurrent.futures.

- timestamp: 2026-04-05T00:00:00Z
  checked: delivery/ai.py lines 31-33 and delivery/fetcher.py
  found: _build_prompt sends ALL articles from all RSS feeds for a theme. Privacy & Security has 2 feeds (eff.org, wired.com). Log says "70 articles fetched". The prompt JSON-encodes all 70 articles with url+title+description. Each article description can be 200-500 chars. 70 * 400 chars avg = 28000 chars of article data + prompt overhead. This exceeds Gemini 2.5 Flash's JSON output limits, causing JSON parse error. Retry on Gemini 2.0 Flash hits 429 quota. Groq gets 413 because the HTTP request body is too large.
  implication: No article count cap before AI call. Fix: limit articles sent to AI to a reasonable maximum (e.g. 15-20).

- timestamp: 2026-04-05T00:00:00Z
  checked: delivery/poster.py lines 21-24 and 35-43
  found: format_post uses parse_mode="Markdown" (legacy Telegram Markdown). It includes article['title'] and article['summary'] directly in the message with *bold* formatting. AI-generated titles/summaries routinely contain characters that are special in Telegram Markdown: *, _, [, ], (, ). For example, a title like "New SDK (v2.0) released - What's next?" contains ( ) which break inline links in Markdown mode. Telegram returns 400 Bad Request when the Markdown is invalid.
  implication: Unescaped special characters in AI-generated content break Telegram's legacy Markdown parser. Fix: either switch to parse_mode="MarkdownV2" with proper escaping, or use HTML parse mode, or strip/escape special chars before sending.

- timestamp: 2026-04-05T00:00:00Z
  checked: db/client.py lines 39-54 and 57-77
  found: Both execute() and execute_many() use requests.post() with timeout=10 (hardcoded). No retry logic. Turso HTTP endpoint (sqld) can have cold-start latency or brief network hiccups that exceed 10s, causing the connection timeout seen in 2026-04-02 logs. Each DB call is a fresh HTTP request with TCP+TLS handshake overhead.
  implication: A single transient network hiccup causes a hard failure with no retry. Fix: add retry with exponential backoff (2-3 retries) for timeout errors specifically.

## Resolution
<!-- OVERWRITE as understanding evolves -->

root_cause: |
  Five independent root causes:
  1. TIMING: GitHub Actions cron scheduler has inherent 5-30 min queue delay, plus pip install without caching adds ~90-120s on every run. Combined: 27+ min late arrival.
  2. SEQUENTIAL: delivery/main.py processes themes in a serial for-loop. 5 themes * ~80s (AI call dominated) = 400s total. No concurrency.
  3. AI_EMPTY (Privacy & Security): No article count cap before calling AI. With 70 articles, the prompt JSON payload exceeds Gemini token limits (JSON parse error), then hits 429 quota on Gemini retry, then 413 on Groq (HTTP payload too large).
  4. 400 BAD REQUEST (Software Development): poster.py used parse_mode="Markdown" (legacy) but AI-generated titles/summaries contain unescaped Telegram Markdown special chars (parentheses, dashes, dots etc.), causing Telegram to reject the message.
  5. TURSO TIMEOUT: db/client.py uses requests with timeout=10s and zero retry logic. A single transient network hiccup causes a hard failure.

fix: |
  1. TIMING: Added `cache: "pip"` to setup-python step in deliver.yml. Saves ~90s per run. GitHub Actions queue delay (up to 15-27 min) is a platform constraint — cannot be eliminated but pip caching reduces controllable overhead. Note: if sub-minute precision is required, migration to a dedicated cron runner (e.g. Railway, Render cron) is needed.
  2. SEQUENTIAL: Refactored delivery/main.py to use ThreadPoolExecutor (max 5 workers). All themes processed in parallel. Expected run time: ~80s (dominated by slowest single theme) vs 400s before.
  3. AI_EMPTY: Added MAX_ARTICLES_PER_PROMPT = 15 constant in delivery/ai.py. Articles are sliced to this cap before building the AI prompt. Prevents token overflow and Groq 413.
  4. 400 BAD REQUEST: Switched delivery/poster.py from parse_mode="Markdown" to parse_mode="MarkdownV2". Added _escape_mdv2() function that escapes all 18 MarkdownV2 special characters. Applied to title, summary, hashtags, URL, and importance_detail before sending.
  5. TURSO TIMEOUT: Added _post_with_retry() in db/client.py that retries up to 3 times on ConnectTimeout, ReadTimeout, ConnectionError with 1s/2s backoff. Timeout per attempt raised from 10s to 15s.

verification: 98/98 tests pass after all fixes. Test for format_post updated to account for MarkdownV2 escaping.
files_changed:
  - .github/workflows/deliver.yml
  - delivery/main.py
  - delivery/ai.py
  - delivery/poster.py
  - db/client.py
  - tests/test_poster.py
