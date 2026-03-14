# Jobert

A lightweight, **serverless** job scraper that tracks new Software Engineering,
AI, Quant internships, and Spring Weeks — hosted 100 % free on GitHub Actions
and delivered straight to a Telegram group chat.

---

## How it works

| Component      | Technology                                   |
| -------------- | -------------------------------------------- |
| Language       | Python 3.11                                  |
| Scheduling     | GitHub Actions (`cron` — every 6 hours)      |
| Notifications  | Telegram Bot API (`requests`)                |
| State tracking | `seen_jobs.json` committed back to this repo |

### Sources scraped

1. **Trackr** — queries the backend programmes API  
   (`https://api.the-trackr.com/programmes?region=UK&industry=Technology&season=2026&type=summer-internships`)

---

## One-time setup

### 1 · Create a Telegram Bot

1. Open Telegram and start a chat with **@BotFather**.
2. Send `/newbot` and follow the prompts to choose a name and username.
3. BotFather will reply with your **Bot Token** — copy it (looks like
   `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`).

### 2 · Get your Telegram Chat ID

1. Add the bot to your group (or use a private chat).
2. Send any message in that chat.
3. Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in your browser.
4. Find `"chat": {"id": -100XXXXXXXXXX}` — that number is your **Chat ID**
   (group IDs are negative).

### 3 · Add GitHub Repository Secrets

1. Go to your repository → **Settings** → **Secrets and variables** →
   **Actions** → **New repository secret**.
2. Add two secrets:

   | Name             | Value                        |
   | ---------------- | ---------------------------- |
   | `TELEGRAM_TOKEN` | The bot token from BotFather |
   | `CHAT_ID`        | Your Telegram chat/group ID  |

### 4 · Enable GitHub Actions (if not already enabled)

Go to **Actions** tab → click **"I understand my workflows, go ahead and
enable them"** if prompted.

### 5 · (Optional) Trigger a first run manually

Actions tab → **Job Scraper** → **Run workflow** → **Run workflow**.

---

## File structure

```
.
├── .github/
│   └── workflows/
│       └── scraper.yml   # GitHub Actions workflow (runs every 6 h)
├── scraper.py             # Main scraper + notification logic
├── requirements.txt       # Python dependencies
├── seen_jobs.json         # Persisted list of already-notified job IDs
└── README.md
```

---

## Customisation

- **Add new sources** — add a new `scrape_*()` function in `scraper.py` and
  call it inside `run()`.
- **Change the schedule** — edit the `cron` expression in
  `.github/workflows/scraper.yml`.
- **Filter different roles** — update the `_ROLE_KEYWORDS` regex in
  `scraper.py`.
- **Trackr endpoint** — update `TRACKR_API_URL` query parameters if you want a
  different region, industry, season, or programme type.
