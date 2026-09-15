# Jobert

Jobert is an AI-powered job application assistant that tracks internships and helps you prepare applications using your CV and a Notion-based Knowledge Base.

---

## Architecture

| Component | Technology |
| :--- | :--- |
| **Scraper** | Python 3.11 (GitHub Actions) |
| **Orchestrator** | FastAPI |
| **Onboarding Bot** | Telegram Bot API (`python-telegram-bot`) |
| **Database** | Supabase (Postgres + Storage) |
| **AI Agent** | Gemini 3 Flash |
| **Knowledge Base** | Notion API |

---

## One-time Setup

### 1 · Telegram Configuration
1. **Create a Bot**: Chat with [@BotFather](https://t.me/BotFather), send `/newbot`, and save your **Bot Token**.
2. **Get Chat ID**:
   - Add your bot to a group.
   - Send a message (e.g., `/test`).
   - Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`.
   - Copy the `id` from the `"chat"` object (e.g., `-100...`).

### 2 · Supabase Configuration
1. **Database**: Run the SQL in `schema.sql` in your Supabase SQL Editor.
2. **Storage**: Create a **public** bucket named `cv_storage` in Supabase Storage.
3. **Credentials**: Copy your `SUPABASE_URL` and `SUPABASE_KEY` (service_role) from **Project Settings → API**.

### 3 · Encryption Key
Generate a secure 32-byte key for encrypting user tokens:
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 4 · Notion Integration
1. Go to [Notion Integrations](https://www.notion.so/my-integrations).
2. Create a new "Internal Integration".
3. **IMPORTANT**: On a page in your Notion workspace, click `...` → `Connect to` → Select your integration. This allows the bot to create your KB page.

---

## Running the Application

### Local Development
1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install -r backend/requirements.txt
   ```
2. **Configure `.env`**: Copy `.env.example` to `.env` and fill in all values.
3. **Start the Onboarding Bot**:
   ```bash
   python -m backend.bot
   ```
4. **Start the API Orchestrator**:
   ```bash
   uvicorn backend.main:app --reload
   ```

### Deployment
The scraper continues to run on **GitHub Actions**. The backend (FastAPI + Bot) is designed to run on **Fly.io**, **DigitalOcean**, or any persistent VPS.

### API health alerts
Before sending job notifications, the scheduled scraper checks that Trackr still
returns usable programme lists and the fields Jobert depends on, including
`openingDate`. Invalid JSON,
request failures, missing programme fields, changed response wrappers, or empty
results across every configured season pause the scrape and send a Telegram API
alert with a link to the failed GitHub Actions run.

Jobert only notifies programmes with a confirmed opening date on or before today,
no past closing date, and a reachable external link. Missing or invalid
dates are treated as unconfirmed. Each eligible programme not already in
`seen_jobs.json` gets an individual emoji alert, newest opening date first.
Jobert sends at most 15 per run, waits two seconds between alerts, and defers
any remaining listings to the next run. Only successful sends are added to
`seen_jobs.json`; an empty run sends no job message.
When Trackr supplies no closing date, openings older than 180 days are also
treated as unconfirmed, since an old careers URL can still return HTTP 200.

The reviewed 14-15 September burst shortlist is separate from routine alerts.
The `burst-summary` manual workflow mode sends one clickable Telegram message
from `burst_summary_2026-09-14.json`, then records `sent_at` so later dispatches
do not repeat it. Scheduled runs never send this retrospective summary.

Jobert stores the failure fingerprint in `api_health.json`, so it sends one alert
per distinct problem instead of repeating it every six hours. It sends a recovery
message when the API becomes usable again. The workflow commits this health state
even when the scraper fails.

---

## Project Structure
```
.
├── backend/
│   ├── bot.py           # Telegram Onboarding Flow
│   ├── database.py      # Supabase & Storage interactions
│   ├── encryption.py    # Fernet encryption for secrets
│   ├── notion_api.py    # Notion KB creation & population
│   └── main.py          # FastAPI Orchestrator
├── schema.sql           # Database schema
├── scraper.py           # Legacy scraper (GitHub Actions)
└── SPECIFICATION.md     # Technical roadmap
```
