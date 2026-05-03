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
