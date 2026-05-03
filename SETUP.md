# Jobert Setup Guide

This guide will walk you through setting up the four external services required to run Jobert.

---

## 1. Telegram (The Interface)
Jobert uses two parts of Telegram: a **Bot** for 1-on-1 setup and a **Group Chat** for job alerts.

### A. Create the Bot
1. Open [BotFather](https://t.me/BotFather) in Telegram.
2. Send `/newbot` and follow the instructions.
3. Save the **API Token** (e.g., `8684241794:AAH4ArTj...`).
4. **Important**: Go to your bot's settings in BotFather → **Bot Settings** → **Allow Groups** → Ensure it is **ON**.

### B. Get the Group Chat ID
1. Create a Telegram Group and add your bot to it.
2. Send a message to the group and tag your bot (e.g. `@YourBotName hello`).
3. Open this link in your browser: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`.
4. Look for the `id` inside the `chat` object (it will be a negative number like `-5283987702`).

---

## 2. Supabase (The Database)
Jobert stores your encrypted tokens and your CV files here.

### A. Project Setup
1. Create a free project at [supabase.com](https://supabase.com).
2. Go to **Project Settings → API** and copy your:
   - `Project URL`
   - `service_role` key (Required for admin access to storage).

### B. Database & Storage
1. Open the **SQL Editor** in Supabase and paste/run the contents of `schema.sql`.
2. Go to **Storage**, click **New Bucket**, name it `cv_storage`, and set it to **Public**.

---

## 3. Notion (The Knowledge Base)
This is where your AI-generated applications will be stored.

### A. Create an Integration
1. Go to [Notion - My Integrations](https://www.notion.so/my-integrations).
2. Click **+ New integration**, name it "Jobert", and select your workspace.
3. Copy the **Installation Access Token**.

### B. Connect a Page
1. Create a page in Notion (e.g., "Job Hunt 2026").
2. Click the **`...`** (top right) → **Connect to** → Search for "Jobert" → **Confirm**.
3. Copy the **URL** of this page. You will need it during onboarding.

---

## 4. Google Gemini (The AI)
Gemini 3 Flash handles the scraping and answer generation.

1. Go to [Google AI Studio](https://aistudio.google.com/).
2. Click **Get API key** → **Create API key in new project**.
3. Copy the key.

---

## 5. Environment Configuration
1. Copy `.env.example` to `.env`.
2. Fill in all the keys you gathered above.
3. Generate your `ENCRYPTION_KEY` by running this in your terminal:
   ```bash
   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

---

## 6. Run Onboarding
Once `.env` is ready:
1. Install dependencies: `pip install -r backend/requirements.txt`.
2. Run the bot: `python -m backend.bot`.
3. Open a **Private DM** with your bot on Telegram and send `/start`.
