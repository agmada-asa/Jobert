"""
Jobert — lightweight, serverless job scraper.

Targets:
  1. Trackr JSON API (mock / real endpoint)
  2. Simplify open-source internship tracker (GitHub raw Markdown)

State is persisted in seen_jobs.json and committed back to the repo by the
GitHub Actions workflow so duplicate notifications are never sent.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Configuration (injected via environment variables / GitHub Actions secrets)
# ---------------------------------------------------------------------------

TELEGRAM_TOKEN: str = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID: str = os.environ.get("CHAT_ID", "")

SEEN_JOBS_FILE: str = "seen_jobs.json"

# Request headers that mimic a real browser to reduce the chance of blocks.
HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}

# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------


def load_seen_jobs() -> list[str]:
    """Return the list of already-notified job IDs."""
    if not os.path.exists(SEEN_JOBS_FILE):
        return []
    with open(SEEN_JOBS_FILE, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        return []
    return [str(item) for item in data]


def save_seen_jobs(seen: list[str]) -> None:
    """Overwrite seen_jobs.json with the updated list."""
    with open(SEEN_JOBS_FILE, "w", encoding="utf-8") as fh:
        json.dump(seen, fh, indent=2)


# ---------------------------------------------------------------------------
# Telegram notifications
# ---------------------------------------------------------------------------


def send_telegram_message(text: str) -> bool:
    """
    Send an HTML-formatted message to the configured Telegram chat.

    Returns True on success, False on failure.
    """
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("WARNING: TELEGRAM_TOKEN or CHAT_ID is not set — skipping notification.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload: dict[str, Any] = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        return True
    except requests.RequestException as exc:
        print(f"ERROR sending Telegram message: {exc}")
        return False


def format_job_message(job: dict[str, str]) -> str:
    """Return a clean, HTML-formatted Telegram message for a single job."""
    role = job.get("role", "Unknown Role")
    company = job.get("company", "Unknown Company")
    link = job.get("link", "#")
    return (
        f"🆕 <b>{role}</b>\n"
        f"🏢 <i>{company}</i>\n"
        f'🔗 <a href="{link}">Apply here</a>'
    )


# ---------------------------------------------------------------------------
# Scraper 1 — Trackr JSON API (mock / real)
# ---------------------------------------------------------------------------

# Replace this URL with the real Trackr hidden API endpoint once discovered
# (e.g. via browser DevTools → Network tab).
TRACKR_API_URL = "https://trackr.lol/api/opportunities"

# Keywords used to filter relevant opportunities.
_ROLE_KEYWORDS = re.compile(
    r"intern|internship|spring\s*week|placement|co.?op|"
    r"software\s*eng|swe|ai|ml|machine\s*learning|quant",
    re.IGNORECASE,
)


def _is_relevant(title: str) -> bool:
    return bool(_ROLE_KEYWORDS.search(title))


def scrape_trackr() -> list[dict[str, str]]:
    """
    Fetch jobs from the Trackr hidden JSON API.

    Expected API response shape (array of objects):
        [
          {
            "id": "abc123",
            "title": "Software Engineering Intern",
            "company": "Acme Corp",
            "url": "https://apply.example.com/job/abc123"
          },
          ...
        ]

    Returns a normalised list:
        [{"id": str, "role": str, "company": str, "link": str}, ...]
    """
    jobs: list[dict[str, str]] = []
    try:
        response = requests.get(TRACKR_API_URL, headers=HEADERS, timeout=20)
        response.raise_for_status()
        data: list[dict[str, Any]] = response.json()
    except requests.RequestException as exc:
        print(f"WARNING: Could not reach Trackr API: {exc}")
        return jobs
    except ValueError as exc:
        print(f"WARNING: Trackr API returned invalid JSON: {exc}")
        return jobs

    for item in data:
        title: str = str(item.get("title", ""))
        if not _is_relevant(title):
            continue
        job_id = str(item.get("id", ""))
        if not job_id:
            continue
        jobs.append(
            {
                "id": f"trackr_{job_id}",
                "role": title,
                "company": str(item.get("company", "Unknown")),
                "link": str(item.get("url", "#")),
            }
        )
    print(f"Trackr: found {len(jobs)} relevant jobs.")
    return jobs


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


def run() -> None:
    """
    Main entry-point:
      1. Load previously seen job IDs.
      2. Fetch jobs from all sources.
      3. Send Telegram notifications for new jobs.
      4. Persist updated state.
    """
    seen: list[str] = load_seen_jobs()
    seen_set: set[str] = set(seen)

    all_jobs: list[dict[str, str]] = []
    all_jobs.extend(scrape_trackr())

    new_jobs = [job for job in all_jobs if job["id"] not in seen_set]
    print(f"Total new jobs to notify: {len(new_jobs)}")

    newly_sent: list[str] = []
    for job in new_jobs:
        message = format_job_message(job)
        success = send_telegram_message(message)
        if success:
            newly_sent.append(job["id"])
            print(f"  ✓ Notified: {job['role']} @ {job['company']}")
        else:
            print(f"  ✗ Failed to notify: {job['role']} @ {job['company']}")

    if newly_sent:
        seen.extend(newly_sent)
        save_seen_jobs(seen)
        print(f"State updated — {len(newly_sent)} new IDs saved.")
    else:
        print("No new jobs found or all notifications failed — state unchanged.")


if __name__ == "__main__":
    if not TELEGRAM_TOKEN:
        print("ERROR: TELEGRAM_TOKEN environment variable is not set.")
        sys.exit(1)
    if not CHAT_ID:
        print("ERROR: CHAT_ID environment variable is not set.")
        sys.exit(1)
    run()
