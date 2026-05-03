# Jobert AI Application Agent: Technical Specification v2

> Revised architecture based on design review. Prioritises **answer quality and
> review speed** over full browser automation. Ships value at Phase 2; browser
> automation is an optional later phase.

---

## 1. Product Vision

Jobert evolves from a job scraper into a **collaborative, privacy-first application
assistant**. Any member of a group chat can trigger a personalised application
preparation flow. The agent researches the role, synthesises the user's
professional profile, generates tailored answers, and populates a private Notion
page — all without exposing any user data to the group.

---

## 2. Core Workflow

1. **Trigger** — A user replies `/apply` to a job link posted by Jobert in the
   group chat.
2. **User Identification** — The bot checks Supabase for the Telegram User ID.
   - **New user:** Bot opens a private DM and runs the onboarding flow
     (see §6).
   - **Known user:** Bot retrieves their stored profile and proceeds immediately.
3. **Preparation (AI Agent)** — The agent:
   - Scrapes the job URL to extract the description, required fields, and any
     visible form questions.
   - Reads the user's CV and their **Notion Knowledge Base** page.
   - Generates tailored answers for each detected question.
   - Creates and populates a structured **Application Page** in the user's
     private Notion workspace.
4. **Review** — The bot sends the user a private DM containing:
   - A direct link to their Notion Application Page.
   - A concise Telegram summary (role, company, key answers) for quick
     preview without leaving the app.
   - An **[Approve & Submit]** button and a **[Needs Editing]** button.
5. **Submission (Manual-first)** — On approval:
   - **v1 (default):** Bot sends a "ready to apply" confirmation. The user
     applies manually using the Notion page as a reference. The bot provides
     a **[Mark as Submitted]** button to update the Notion page status.
   - **v2 (optional, see §8):** A headless browser agent auto-fills and
     submits the form.
6. **Confirmation** — The Notion page status updates to `Submitted`. A
   lightweight log entry is written to Supabase.

---

## 3. Technical Architecture

| Component | Technology | Reason |
| :--- | :--- | :--- |
| **Orchestrator** | Python (FastAPI) | Async-friendly; consistent with existing scraper codebase |
| **Scheduler / Scraper** | GitHub Actions (existing) | Keep free; no change needed |
| **LLM** | Gemini 2.0 Flash (user-supplied key) | Free tier per user; 1,500 req/day per key |
| **Knowledge Base** | Private Notion API (user-supplied token) | Clean review UI; user already owns the workspace |
| **User Database** | Supabase Free Tier (Postgres) | Maps Telegram IDs to encrypted credentials |
| **CV / File Storage** | Supabase Storage (free tier) | Keeps CVs off Telegram's servers |
| **Hosting** | Fly.io (free tier) or DigitalOcean $4/mo droplet | Persistent process; no cold-start issues; cheaper than Railway |

### Why not Railway?
Railway's cheapest plan ($5/mo) is warranted only when running persistent
Playwright browser instances. Since browser automation is deferred to v2, Fly.io
free tier or a small DigitalOcean droplet is sufficient and cheaper.

---

## 4. Multi-User Privacy Model

- **Individual Notion tokens:** Each user authorises only their own Notion
  workspace. The bot cannot access any other user's pages.
- **Individual Gemini keys:** Each user supplies their own API key. LLM costs
  are zero to the operator.
- **Encrypted storage:** All tokens, API keys, and CV references are encrypted
  at rest in Supabase using a server-side secret.
- **Private DM flow:** All sensitive exchanges (onboarding, review links,
  answer summaries) happen in 1-on-1 DMs with the bot — nothing sensitive is
  ever posted to the group chat.

> **Disclosure note:** During onboarding, inform users that the Gemini free
> tier does not carry paid-tier data privacy guarantees. CVs will pass through
> Google's servers. Users can opt to use a paid key for stronger guarantees.

---

## 5. Knowledge Sourcing (The "Dual Source" Model)

The original "Triple Threat" included LinkedIn scraping, which has been removed
due to LinkedIn's aggressive blocking and the infrastructure overhead required.
The two remaining sources provide equivalent coverage:

| Source | What it provides |
| :--- | :--- |
| **CV** (uploaded during onboarding) | Core professional history, skills, education |
| **Notion Knowledge Base page** | User-controlled factoids: preferences, projects, relocation stance, preferred stack, anything the CV doesn't capture |

The Knowledge Base page is templated during onboarding so users know exactly
what to fill in. The agent reads this page on every `/apply` call.

---

## 6. Onboarding Flow (Phase 1)

Triggered automatically the first time a new user runs `/apply`.

```
Bot DM: "Hey [name]! Let's set up your profile. I'll need a few things."

Step 1 — Notion:
  "Please share your Notion Internal Integration Token.
   (Settings → Integrations → Create new integration)"
  → Bot validates token, stores encrypted in Supabase.
  → Bot creates a templated 'Jobert KB' page in their workspace and
    sends them the link to fill in.

Step 2 — CV:
  "Upload your CV as a PDF."
  → Stored in Supabase Storage, linked to their Telegram ID.

Step 3 — Gemini API Key:
  "Finally, paste your Gemini API key (free at aistudio.google.com).
   This keeps costs at zero and your data in your own account."
  → Stored encrypted in Supabase.

Bot: "All set! You can now use /apply on any job link."
```

Users can update any item later with `/update_cv`, `/update_key`, etc.

---

## 7. Notion Application Page Structure

Auto-created for every `/apply` trigger:

```
📁 [Company Name] — [Role Title]
├── 🔗 Application URL
├── 📋 Job Description Summary
│    └── Key requirements extracted by the agent
├── ❓ Detected Form Questions
│    └── List of questions scraped from the application page
├── ✍️  Generated Answers
│    └── One answer block per question, tailored to the user's profile
├── 📄 CV Version
│    └── Link to the CV used (Supabase URL)
└── ✅ Status
     └── Draft → Reviewed → Submitted
```

---

## 8. Implementation Phases

### Phase 1 — Onboarding & Storage
- Build the DM-based profile setup flow (token, CV, Gemini key).
- Set up encrypted Supabase schema.
- Template the Notion Knowledge Base page.

### Phase 2 — Answer Generation & Notion Population
- Implement the job URL scraper for question extraction.
- Build the Gemini-powered answer generator (CV + KB context).
- Build the Notion template creator and page populator.
- Wire up the DM review flow (link + summary + Approve/Needs Editing buttons).
- Add `[Mark as Submitted]` button and status updater.

> **✓ Shippable milestone.** At the end of Phase 2, the product is fully
> usable. Every subsequent phase is an enhancement, not a prerequisite.

### Phase 3 — Group Integration & Polish
- Bridge the existing `scraper.py` `/apply` command handler to the new FastAPI backend.
- Add `/status` command to list recent applications and their Notion links.
- Per-user job scraping cache: if two users apply to the same listing, parse
  the job description only once (reduces redundant LLM calls).
- Add the ability for users to have alternate CV versions (e.g., "Tech CV", "Finance CV") and select which one to use per application.

### Phase 4 — Browser Automation (Optional)
Only warranted once Phases 1–3 are stable and the answer quality is validated.

- Integrate `browser-use` + `Playwright` on Railway (upgrade hosting at this point).
- Target simpler portals first (Lever, Ashby) before attempting Workday/Greenhouse.
- Implement graceful fallback: if the agent cannot complete the form, it
  notifies the user and reverts to the Phase 2 manual flow.
- **Do not implement auto-account creation.** Programmatic account creation
  on job portals risks IP bans and ToS violations that could affect real
  applications. Prompt the user to create an account manually if one is needed,
  then proceed with form-filling only.

---

## 9. Cost Summary

| Item | Cost |
| :--- | :--- |
| GitHub Actions (scraper) | Free |
| Fly.io / DigitalOcean (FastAPI host) | Free – $4/mo |
| Supabase (database + storage) | Free tier |
| Notion API | Free |
| LLM (Gemini 2.0 Flash, BYOK) | **$0 to operator** |
| **Total** | **$0 – $4/mo** |