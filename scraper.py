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
from datetime import UTC, datetime
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Configuration (injected via environment variables / GitHub Actions secrets)
# ---------------------------------------------------------------------------

TELEGRAM_TOKEN: str = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID: str = os.environ.get("CHAT_ID", "")

SEEN_JOBS_FILE: str = "seen_jobs.json"
JOBS_FILE: str = "jobs.json"

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


def save_job_catalog(jobs: list[dict[str, Any]]) -> None:
    """Merge complete job records into the catalog consumed by the web app."""
    existing: dict[str, dict[str, Any]] = {}
    if os.path.exists(JOBS_FILE):
        try:
            with open(JOBS_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                existing = {str(item["id"]): item for item in data if isinstance(item, dict) and item.get("id")}
        except (OSError, json.JSONDecodeError):
            pass

    timestamp = datetime.now(UTC).isoformat()
    for job in jobs:
        previous = existing.get(str(job["id"]), {})
        existing[str(job["id"])] = {
            **previous,
            **job,
            "first_seen_at": previous.get("first_seen_at") or timestamp,
            "last_seen_at": timestamp,
        }

    with open(JOBS_FILE, "w", encoding="utf-8") as fh:
        json.dump(list(existing.values()), fh, indent=2, ensure_ascii=False)


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

# Trackr programmes API for all currently available UK Tech summer-internship
# seasons. Add newly published seasons here as Trackr makes them available.
TRACKR_API_URL = "https://api.the-trackr.com/programmes"
TRACKR_SEASONS: tuple[str, ...] = ("2026", "2027", "2028")
TRACKR_PARAMS: dict[str, str] = {
    "region": "UK",
    "industry": "Tech",
    "type": "summer-internships",
}

# Keywords used to filter relevant opportunities.
_ROLE_KEYWORDS = re.compile(
    r"intern|internship|spring\s*week|placement|co.?op|"
    r"software\s*eng|swe|ai|ml|machine\s*learning|quant",
    re.IGNORECASE,
)


def _is_relevant(title: str) -> bool:
    return bool(_ROLE_KEYWORDS.search(title))


def scrape_trackr() -> list[dict[str, Any]]:
    """
    Fetch jobs for every configured season from the Trackr hidden JSON API.

        Expected API response shape (array of objects):
        [
          {
                        "id": "03lef43vs8",
                        "name": "Software Engineering Internship",
                        "url": "https://..." | null,
                        "categories": ["Software Engineering"],
                        "company": {
                            "id": "two-sigma",
                            "name": "Two Sigma"
                        }
          },
          ...
        ]

    Returns a normalised list:
        [{"id": str, "role": str, "company": str, "link": str}, ...]
    """
    jobs: list[dict[str, Any]] = []
    seen_job_ids: set[str] = set()

    for season in TRACKR_SEASONS:
        try:
            response = requests.get(
                TRACKR_API_URL,
                params={**TRACKR_PARAMS, "season": season},
                headers=HEADERS,
                timeout=20,
            )
            response.raise_for_status()
            data: Any = response.json()
        except requests.RequestException as exc:
            print(f"WARNING: Could not fetch Trackr season {season}: {exc}")
            continue
        except ValueError as exc:
            print(f"WARNING: Trackr season {season} returned invalid JSON: {exc}")
            continue

        if not isinstance(data, list):
            print(
                f"WARNING: Trackr season {season} response is not a list; skipping."
            )
            continue

        season_jobs = 0
        for item in data:
            job = _normalise_trackr_job(item, season)
            if job is None or job["id"] in seen_job_ids:
                continue
            jobs.append(job)
            seen_job_ids.add(job["id"])
            season_jobs += 1
        print(f"Trackr {season}: found {season_jobs} relevant jobs.")

    print(f"Trackr: found {len(jobs)} relevant jobs across all seasons.")
    return jobs


def _normalise_trackr_job(item: Any, season: str = "") -> dict[str, Any] | None:
    """Validate and normalise one Trackr API programme."""
    if not isinstance(item, dict):
        return None

    role: str = str(item.get("name") or item.get("title") or "")
    categories = item.get("categories")
    categories_text = ""
    if isinstance(categories, list):
        categories_text = " ".join(str(cat) for cat in categories)

    if not _is_relevant(f"{role} {categories_text}".strip()):
        return None

    job_id = str(item.get("id") or "")
    if not job_id:
        return None

    company_info = item.get("company")
    company_name = "Unknown"
    company_description = ""
    if isinstance(company_info, dict):
        company_name = str(company_info.get("name") or "Unknown")
        company_description = str(company_info.get("description") or "").strip()
    elif item.get("company"):
        company_name = str(item.get("company"))

    link = str(item.get("url") or "").strip()
    if not link:
        # Fallback to the public programme page when direct apply URL is missing.
        link = f"https://the-trackr.com/programmes/{job_id}"

    return {
        "id": f"trackr_{job_id}",
        "role": role or "Unknown Role",
        "company": company_name,
        "link": link,
        "location": ", ".join(str(value) for value in (item.get("locations") or []) if value) or "United Kingdom",
        "summary": company_description,
        "source": "trackr",
        "season": str(item.get("season") or season),
        "categories": categories if isinstance(categories, list) else [],
        "closing_date": item.get("closingDate"),
        "cv_required": item.get("cv"),
        "cover_letter_required": item.get("coverLetter"),
    }


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

    all_jobs: list[dict[str, Any]] = []
    all_jobs.extend(scrape_trackr())
    save_job_catalog(all_jobs)
    print(f"Catalog updated — {len(all_jobs)} current jobs are available to the web app.")

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
