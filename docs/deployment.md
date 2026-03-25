# Telegram News Bot — Complete Launch & Maintenance Guide

This guide covers everything from zero to a running bot: creating every account and API key, deploying the code, and keeping the bot healthy after launch.

---

## What You Will Need

| Service | Purpose | Cost |
|---------|---------|------|
| Telegram (@BotFather) | Create the bot, enable Stars payments | Free |
| Vercel | Host the webhook (serverless) | Free tier sufficient |
| Turso | Database (serverless SQLite) | Free tier sufficient |
| Google AI Studio | Gemini API key (AI summaries) | Free tier sufficient |
| Groq | Fallback AI key (Llama) | Free tier sufficient |
| GitHub | Repository + hourly delivery cron | Free |

---

## Part 1 — Get All API Keys

### 1.1 Create the Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Choose a display name (e.g. `My News Bot`)
4. Choose a username ending in `bot` (e.g. `mynewsbot_bot`)
5. BotFather replies with your **Bot Token** — looks like `7123456789:AAF...`
   - Save it as `TELEGRAM_BOT_TOKEN`

**Enable Stars payments:**

1. In BotFather, send `/mybots` → select your bot → **Bot Settings → Payments**
2. Select **Telegram Stars**
3. This is required for the `/upgrade` command to work

**Find your Telegram user ID (for /admin access):**

1. Open Telegram and search for **@userinfobot**
2. Send `/start`
3. It replies with your numeric user ID (e.g. `123456789`)
   - Save it as `OWNER_USER_ID`

---

### 1.2 Create the Turso Database

1. Go to [turso.tech](https://turso.tech) and create a free account
2. Install the Turso CLI:
   ```bash
   # macOS / Linux
   curl -sSfL https://get.tur.so/install.sh | bash

   # Windows (PowerShell)
   winget install chiselstrike.turso
   ```
3. Log in:
   ```bash
   turso auth login
   ```
4. Create a database:
   ```bash
   turso db create telegram-news-bot
   ```
5. Get the database URL:
   ```bash
   turso db show telegram-news-bot
   ```
   Copy the **URL** field — looks like `libsql://telegram-news-bot-yourname.turso.io`
   - Save it as `TURSO_URL`

6. Create an auth token:
   ```bash
   turso db tokens create telegram-news-bot
   ```
   - Save the token as `TURSO_TOKEN`

---

### 1.3 Get the Gemini API Key

1. Go to [aistudio.google.com](https://aistudio.google.com)
2. Sign in with a Google account
3. Click **Get API key** → **Create API key**
4. Copy the key — looks like `AIzaSy...`
   - Save it as `GEMINI_API_KEY`

The bot uses Gemini 2.5 Flash as the primary AI, with Gemini 2.0 Flash as a fallback.

---

### 1.4 Get the Groq API Key

1. Go to [console.groq.com](https://console.groq.com)
2. Sign up for a free account
3. Go to **API Keys** → **Create API Key**
4. Copy the key — looks like `gsk_...`
   - Save it as `GROQ_API_KEY`

Groq/Llama is the final fallback if both Gemini models fail.

---

### 1.5 Decide on Star Prices

Telegram Stars are the in-app currency for payments.

- `STARS_ONETIME_PRICE` — cost of a one-time upgrade (default: `200`)
- `STARS_MONTHLY_PRICE` — cost of a monthly subscription (default: `100`)

You can set these to any integer. 1 Star ≈ $0.013 USD.

---

### 1.6 Generate a Webhook Secret

This protects your webhook endpoint from unauthorized requests.

```bash
# Generate a random secret (any strong random string works)
python -c "import secrets; print(secrets.token_hex(32))"
```

- Save the output as `WEBHOOK_SECRET`

---

## Part 2 — Set Up the Project Locally

### 2.1 Clone and Install

```bash
git clone https://github.com/YOUR_USERNAME/telegram-news-bot.git
cd telegram-news-bot
pip install -r requirements.txt
pip install -r requirements-dev.txt   # for running tests
```

### 2.2 Create the .env File

```bash
cp .env.example .env
```

Open `.env` and fill in every value:

```env
TURSO_URL=libsql://telegram-news-bot-yourname.turso.io
TURSO_TOKEN=your_turso_token_here
TELEGRAM_BOT_TOKEN=7123456789:AAF...
GEMINI_API_KEY=AIzaSy...
GROQ_API_KEY=gsk_...
WEBHOOK_SECRET=your_generated_secret_here
OWNER_USER_ID=123456789
STARS_ONETIME_PRICE=200
STARS_MONTHLY_PRICE=100
```

> `.env` is in `.gitignore` — it will never be committed.

---

### 2.3 Initialize the Database

Apply the schema and seed the default news themes:

```bash
python db/init_db.py
python db/seed_themes.py
```

Expected output:
```
Schema applied.
Seeded 10 themes.
```

This is safe to run multiple times — all statements use `CREATE TABLE IF NOT EXISTS` and `INSERT OR IGNORE`.

### 2.4 Run Tests Locally

```bash
pytest tests/ -v
```

Expected: **91 tests passing**.

---

## Part 3 — Deploy to Vercel

### 3.1 Install the Vercel CLI

```bash
npm install -g vercel
```

### 3.2 Deploy

From the project root:

```bash
vercel --prod
```

- Log in with your Vercel account when prompted
- Accept the defaults (auto-detected as Python project)
- Note the production URL — looks like `https://telegram-news-bot-abc123.vercel.app`

### 3.3 Add Environment Variables in Vercel

Go to **Vercel Dashboard → your project → Settings → Environment Variables** and add all variables:

| Variable | Value |
|----------|-------|
| `TURSO_URL` | Your Turso database URL |
| `TURSO_TOKEN` | Your Turso auth token |
| `TELEGRAM_BOT_TOKEN` | Your bot token from BotFather |
| `GEMINI_API_KEY` | Your Gemini API key |
| `GROQ_API_KEY` | Your Groq API key |
| `WEBHOOK_SECRET` | Your generated webhook secret |
| `OWNER_USER_ID` | Your Telegram numeric user ID |
| `STARS_ONETIME_PRICE` | `200` |
| `STARS_MONTHLY_PRICE` | `100` |

After adding variables, redeploy so they take effect:

```bash
vercel --prod
```

---

## Part 4 — Register the Telegram Webhook

Tell Telegram where to send updates. Replace the placeholders:

```bash
curl -X POST "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://<your-app>.vercel.app/webhook",
    "secret_token": "<WEBHOOK_SECRET>"
  }'
```

Expected response:
```json
{"ok": true, "result": true, "description": "Webhook was set"}
```

Verify it registered correctly:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getWebhookInfo"
```

Look for `"url"` pointing to your Vercel URL and `"pending_update_count": 0`.

---

## Part 5 — Set Up GitHub Actions (Hourly Delivery)

The bot delivers news via a GitHub Actions cron job that runs every hour.

### 5.1 Push to GitHub

```bash
git remote add origin https://github.com/YOUR_USERNAME/telegram-news-bot.git
git push -u origin master
```

### 5.2 Add GitHub Secrets

Go to **GitHub → Repository → Settings → Secrets and variables → Actions → New repository secret** and add:

- `TURSO_URL`
- `TURSO_TOKEN`
- `TELEGRAM_BOT_TOKEN`
- `GEMINI_API_KEY`
- `GROQ_API_KEY`

> `WEBHOOK_SECRET` and `OWNER_USER_ID` are not needed here — they are only used by the webhook, not the delivery script.

The workflow file is already in the repo at `.github/workflows/deliver.yml`. GitHub will pick it up automatically after the first push.

### 5.3 Verify the First Run

1. Go to **GitHub → Actions → Deliver News Digests**
2. Click **Run workflow** to trigger it manually
3. Watch the logs — you should see themes being processed

If no users have a schedule set yet, the run will complete with no deliveries sent (this is normal).

---

## Part 6 — First Launch Checklist

Run through this after deployment:

- [ ] Open your bot in Telegram and send `/start`
- [ ] Browse themes with `/themes` and subscribe to one
- [ ] Set a delivery schedule with `/schedule`
- [ ] Trigger a manual delivery run in GitHub Actions
- [ ] Confirm the article arrives in Telegram with reaction buttons (thumbs up/down)
- [ ] Tap a reaction button — expect a "👍 Noted!" toast
- [ ] Send `/admin` — confirm the health dashboard appears (owner only)
- [ ] Send `/upgrade` — confirm the Stars payment flow launches
- [ ] Verify webhook is live: send any message to the bot and it responds

---

## Part 7 — Maintenance

### Monitoring Delivery Runs

Every hourly delivery is logged in GitHub Actions:

**GitHub → Actions → Deliver News Digests**

Each run shows:
- How many themes were processed
- Any RSS feed errors
- Any AI API errors or fallbacks

### Bot Health Dashboard

Send `/admin` to the bot (owner only) to see:

- **Active users (7d)** — users who received at least one digest in the last 7 days
- **Deliveries/hour** — digests sent in the last hour
- **Revenue** — total Telegram Stars collected
- **Recent errors** — last 5 delivery errors with timestamps

### Checking Logs

Vercel (webhook errors):

1. Vercel Dashboard → Project → **Deployments** → click latest → **Functions** tab
2. Or use the CLI: `vercel logs`

GitHub Actions (delivery errors):

1. GitHub → Actions → click any run → expand **Run delivery** step

### Rotating API Keys

If you need to rotate a key (e.g. Gemini key is compromised):

1. Generate the new key at the provider's dashboard
2. Update it in **Vercel → Environment Variables**
3. Update it in **GitHub → Secrets**
4. Run `vercel --prod` to redeploy with the new key
5. Update your local `.env` file

### Updating the Database Schema

If a future update adds new tables:

```bash
# Pull latest code
git pull

# Apply schema changes (always safe — uses CREATE TABLE IF NOT EXISTS)
python db/init_db.py
```

### Running Tests After Code Changes

```bash
pytest tests/ -v
```

All 91 tests should pass before deploying any changes.

### Deploying Code Updates

```bash
git add <changed files>
git commit -m "description of change"
git push
vercel --prod
```

---

## Part 8 — Troubleshooting

### Bot not responding to messages

1. Check webhook is registered: `curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"`
2. Check Vercel function logs for errors
3. Confirm `TELEGRAM_BOT_TOKEN` is correct in Vercel env vars

### Delivery not running

1. Check GitHub Actions is enabled: **GitHub → Actions → (enable if disabled)**
2. Manually trigger a run to see the error
3. Confirm all 5 secrets are set in GitHub

### "Not authorized" on /admin

Your `OWNER_USER_ID` in Vercel env vars doesn't match your actual Telegram user ID.

1. Message @userinfobot in Telegram to get your correct ID
2. Update `OWNER_USER_ID` in Vercel env vars
3. Redeploy: `vercel --prod`

### AI summaries failing

The bot uses a fallback chain: Gemini 2.5 Flash → Gemini 2.0 Flash → Groq Llama.

If all three fail, check:
- `GEMINI_API_KEY` is valid and not rate-limited (Google AI Studio dashboard)
- `GROQ_API_KEY` is valid (Groq console)
- GitHub Actions logs for specific error messages

### Database connection errors

1. Confirm `TURSO_URL` includes the full `libsql://` prefix
2. Confirm the token hasn't expired: `turso db tokens create telegram-news-bot` to generate a new one
3. Update `TURSO_TOKEN` in both Vercel and GitHub secrets

---

## Quick Reference — All Environment Variables

| Variable | Where to get it | Required for |
|----------|----------------|-------------|
| `TURSO_URL` | `turso db show <name>` | Everything |
| `TURSO_TOKEN` | `turso db tokens create <name>` | Everything |
| `TELEGRAM_BOT_TOKEN` | @BotFather `/newbot` | Everything |
| `GEMINI_API_KEY` | aistudio.google.com | AI summaries |
| `GROQ_API_KEY` | console.groq.com | AI fallback |
| `WEBHOOK_SECRET` | `python -c "import secrets; print(secrets.token_hex(32))"` | Webhook security |
| `OWNER_USER_ID` | @userinfobot in Telegram | `/admin` command |
| `STARS_ONETIME_PRICE` | Your choice (integer, default 200) | Payments |
| `STARS_MONTHLY_PRICE` | Your choice (integer, default 100) | Payments |

---

## Quick Reference — One-Time Setup Commands

```bash
# Database
python db/init_db.py        # create all tables
python db/seed_themes.py    # add default news themes

# Deploy
vercel --prod               # deploy to Vercel

# Register webhook (replace values)
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://<your-app>.vercel.app/webhook", "secret_token": "<WEBHOOK_SECRET>"}'

# Tests
pytest tests/ -v            # should show 91 passed
```
