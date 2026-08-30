"""
Jobert — lightweight, serverless job scraper.

Targets:
  1. Trackr JSON API (mock / real endpoint)
  2. Simplify open-source internship tracker (GitHub raw Markdown)

State is persisted in seen_jobs.json and committed back to the repo by the
GitHub Actions workflow so duplicate notifications are never sent.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Configuration (injected via environment variables / GitHub Actions secrets)
# ---------------------------------------------------------------------------

TELEGRAM_TOKEN: str = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID: str = os.environ.get("CHAT_ID", "")

SEEN_JOBS_FILE: str = "seen_jobs.json"
API_HEALTH_FILE: str = "api_health.json"

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


def _load_api_health() -> dict[str, Any]:
    """Load the persisted API alert state."""
    if not os.path.exists(API_HEALTH_FILE):
        return {"status": "healthy", "recovery_notified": True}
    try:
        with open(API_HEALTH_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"WARNING: Could not load {API_HEALTH_FILE}: {exc}")
        return {"status": "healthy", "recovery_notified": True}
    if not isinstance(data, dict):
        return {"status": "healthy", "recovery_notified": True}
    return data


def _save_api_health(state: dict[str, Any]) -> None:
    """Persist API alert state so repeated failures do not spam Telegram."""
    with open(API_HEALTH_FILE, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
        fh.write("\n")


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


def _github_run_url() -> str:
    """Return the current GitHub Actions run URL when available."""
    server = os.environ.get("GITHUB_SERVER_URL", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if not all((server, repository, run_id)):
        return ""
    return f"{server}/{repository}/actions/runs/{run_id}"


def _api_issue_fingerprint(issues: list[str]) -> str:
    """Return a stable identifier for one API failure shape."""
    payload = "\n".join(sorted(issues)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _format_api_failure_message(issues: list[str]) -> str:
    """Build the one-off Telegram alert for an API failure."""
    details = html.escape("\n".join(f"- {issue}" for issue in issues))
    message = (
        "<b>Jobert API alert</b>\n"
        "Trackr's response no longer matches Jobert's expected contract. "
        "Job notifications are paused until the response is valid again.\n\n"
        f"<code>{details}</code>"
    )
    run_url = _github_run_url()
    if run_url:
        message += f'\n\n<a href="{html.escape(run_url, quote=True)}">Open GitHub run</a>'
    return message


def _record_api_failure(issues: list[str]) -> None:
    """Alert once for a distinct API failure and persist its fingerprint."""
    fingerprint = _api_issue_fingerprint(issues)
    previous = _load_api_health()
    already_notified = (
        previous.get("status") == "unhealthy"
        and previous.get("fingerprint") == fingerprint
        and previous.get("notified") is True
    )
    if already_notified:
        print(f"API alert {fingerprint} was already sent; not sending it again.")
        return

    sent = send_telegram_message(_format_api_failure_message(issues))
    same_failure = (
        previous.get("status") == "unhealthy"
        and previous.get("fingerprint") == fingerprint
    )
    state = {
        "status": "unhealthy",
        "fingerprint": fingerprint,
        "issues": issues,
        "notified": sent,
        "detected_at": (
            previous.get("detected_at")
            if same_failure and previous.get("detected_at")
            else datetime.now(timezone.utc).isoformat()
        ),
    }
    _save_api_health(state)
    if sent:
        print(f"Sent API alert {fingerprint} to Telegram.")
    else:
        print(f"Could not send API alert {fingerprint}; the next run will retry.")


def _record_api_recovery() -> None:
    """Send one recovery message after a previously reported API failure."""
    previous = _load_api_health()
    needs_recovery = previous.get("status") == "unhealthy"
    retry_recovery = (
        previous.get("status") == "healthy"
        and previous.get("recovery_notified") is False
    )
    if not needs_recovery and not retry_recovery:
        return

    message = (
        "<b>Jobert API recovered</b>\n"
        "Trackr's response matches the expected contract again. "
        "Job notifications have resumed."
    )
    run_url = _github_run_url()
    if run_url:
        message += f'\n\n<a href="{html.escape(run_url, quote=True)}">Open GitHub run</a>'
    sent = send_telegram_message(message)
    state = {
        "status": "healthy",
        "recovery_notified": sent,
        "recovered_at": (
            previous.get("recovered_at")
            if retry_recovery and previous.get("recovered_at")
            else datetime.now(timezone.utc).isoformat()
        ),
    }
    _save_api_health(state)
    if sent:
        print("Sent Trackr API recovery message to Telegram.")
    else:
        print("Could not send the API recovery message; the next run will retry.")


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


class TrackrApiError(RuntimeError):
    """Raised when Trackr is unavailable or breaks the expected API contract."""

    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__("Trackr API check failed: " + "; ".join(issues))


def _is_relevant(title: str) -> bool:
    return bool(_ROLE_KEYWORDS.search(title))


def scrape_trackr() -> list[dict[str, str]]:
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
    jobs: list[dict[str, str]] = []
    seen_job_ids: set[str] = set()
    valid_responses = 0
    programme_count = 0
    issues: list[str] = []

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
            issue = f"season {season}: request failed: {exc}"
            print(f"WARNING: {issue}")
            issues.append(issue)
            continue
        except ValueError as exc:
            issue = f"season {season}: response was not valid JSON: {exc}"
            print(f"WARNING: {issue}")
            issues.append(issue)
            continue

        programmes = _extract_programmes(data)
        if programmes is None:
            issue = (
                f"season {season}: expected a programmes list, received "
                f"{_describe_response(data)}"
            )
            print(f"WARNING: {issue}")
            issues.append(issue)
            continue

        contract_issues = _programme_contract_issues(programmes, season)
        if contract_issues:
            for issue in contract_issues:
                print(f"WARNING: {issue}")
            issues.extend(contract_issues)
            continue

        valid_responses += 1
        programme_count += len(programmes)

        season_jobs = 0
        for item in programmes:
            job = _normalise_trackr_job(item)
            if job is None or job["id"] in seen_job_ids:
                continue
            jobs.append(job)
            seen_job_ids.add(job["id"])
            season_jobs += 1
        print(f"Trackr {season}: found {season_jobs} relevant jobs.")

    if valid_responses == 0 and not issues:
        issues.append("no configured season returned a usable programmes list")
    elif valid_responses > 0 and programme_count == 0:
        issues.append("all configured seasons returned empty programmes lists")

    if issues:
        raise TrackrApiError(issues)

    print(f"Trackr: found {len(jobs)} relevant jobs across all seasons.")
    return jobs


def _extract_programmes(data: Any) -> list[Any] | None:
    """Return programme records from the current or legacy Trackr response."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("programmes"), list):
        return data["programmes"]
    return None


def _describe_response(data: Any) -> str:
    """Describe a response shape without including programme data."""
    if isinstance(data, dict):
        keys = ", ".join(sorted(str(key) for key in data)) or "no keys"
        return f"an object with keys: {keys}"
    if isinstance(data, list):
        return "a list"
    return type(data).__name__


def _programme_contract_issues(programmes: list[Any], season: str) -> list[str]:
    """Detect breaking changes to fields used by the normaliser."""
    if not programmes:
        return []
    records = [item for item in programmes if isinstance(item, dict)]
    if not records:
        return [f"season {season}: programmes contains no object records"]

    required_fields = {
        "id": lambda item: bool(item.get("id")),
        "name or title": lambda item: bool(item.get("name") or item.get("title")),
        "company": lambda item: bool(item.get("company")),
    }
    missing = [
        field
        for field, is_present in required_fields.items()
        if not any(is_present(item) for item in records)
    ]
    if not missing:
        return []
    return [
        f"season {season}: programme records have no usable {', '.join(missing)} field"
    ]


def _normalise_trackr_job(item: Any) -> dict[str, str] | None:
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
    if isinstance(company_info, dict):
        company_name = str(company_info.get("name") or "Unknown")
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
    }


# ---------------------------------------------------------------------------
# Link Verification
# ---------------------------------------------------------------------------


def _is_active(link: str) -> bool:
    """Check if the given apply link actually resolves to an active application page."""
    if not link:
        return False
        
    # If the link is already a trackr programme page, it's preemptive/not active.
    if "the-trackr.com/programmes/" in link:
        return False
        
    try:
        response = requests.get(link, headers=HEADERS, allow_redirects=True, timeout=10)
        # If it redirected to a trackr programme page, the original link is not active.
        if "the-trackr.com/programmes/" in response.url:
            return False
            
        # Treat 404 or server errors as inactive
        if response.status_code >= 400:
            return False
            
        return True
    except requests.RequestException:
        # Fails to connect/timeout -> assume inactive to avoid false positives.
        return False


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
    try:
        all_jobs.extend(scrape_trackr())
    except TrackrApiError as exc:
        _record_api_failure(exc.issues)
        raise
    _record_api_recovery()

    new_jobs = [job for job in all_jobs if job["id"] not in seen_set]
    
    active_new_jobs = []
    for job in new_jobs:
        if _is_active(job["link"]):
            active_new_jobs.append(job)
        else:
            print(f"Skipping inactive job: {job['role']} @ {job['company']}")

    print(f"Total new active jobs to notify: {len(active_new_jobs)}")

    newly_sent: list[str] = []
    for job in active_new_jobs:
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
