# Phase 3: New Features - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-25
**Phase:** 03-new-features
**Areas discussed:** Admin command scope, Reaction button behavior, Delivery tracking schema

---

## Admin Command Scope

| Option | Description | Selected |
|--------|-------------|----------|
| OWNER_USER_ID env var | Set OWNER_USER_ID=<your_telegram_id> in .env. Command rejects anyone else. | ✓ |
| Hardcoded in .env only | Same idea but no dedicated env var name | |

**User's choice:** OWNER_USER_ID env var

---

| Option | Description | Selected |
|--------|-------------|----------|
| Received a delivery in last 7 days | Query digest_history for users with sent_at > now-7d | ✓ |
| Has any user_themes row | All users with at least one subscribed theme | |
| Used the bot in last 7 days | Would require last_active column schema change | |

**User's choice:** Received a delivery in last 7 days

---

| Option | Description | Selected |
|--------|-------------|----------|
| Add delivery_errors table | Insert on each delivery exception, admin shows last 5 | ✓ |
| Skip errors for now | Leave recent errors out of /admin v1 | |
| Parse logs at query time | Not viable on Vercel serverless | |

**User's choice:** Add delivery_errors table

---

| Option | Description | Selected |
|--------|-------------|----------|
| Single message with sections | One Markdown message with emoji section headers | ✓ |
| Multiple short messages | One message per section | |

**User's choice:** Single message with sections

---

## Reaction Button Behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Silent save + toast | Store reaction, show brief toast via answerCallbackQuery | ✓ |
| Edit message to show count | Update article message buttons to show counts | |

**User's choice:** Silent save + toast

---

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — last reaction wins | INSERT OR REPLACE on (user_id, article_url) | ✓ |
| No — first reaction is final | INSERT OR IGNORE | |

**User's choice:** Yes — last reaction wins

---

| Option | Description | Selected |
|--------|-------------|----------|
| Use article URL as the key | Consistent with posted_articles dedup table | ✓ |
| Use message_id from Telegram | Requires storing message_id from post_article return | |

**User's choice:** Use article URL as the key

---

## Delivery Tracking Schema

| Option | Description | Selected |
|--------|-------------|----------|
| Per-article per-user | One row per article per user: (user_id, article_url, status, sent_at) | ✓ |
| Per-theme per-user | One row per theme delivery per user — coarser but lighter | |

**User's choice:** Per-article per-user

---

| Option | Description | Selected |
|--------|-------------|----------|
| 'sent' \| 'failed' only | Simple binary, enough to answer "did this user get this article?" | ✓ |
| 'sent' \| 'failed' \| 'skipped' | Also track deduped/skipped articles | |

**User's choice:** 'sent' | 'failed' only

---

## Claude's Discretion

- Exact SQL DDL for new tables
- Batch vs per-article delivery_log insertion strategy
- Reaction toast message text
- /admin edge case handling (zero states)

## Deferred Ideas

None surfaced during discussion.
