"""
Jobert — lightweight, serverless job scraper.

Targets:
  1. Trackr JSON API (mock / real endpoint)
  2. Simplify open-source internship tracker (GitHub raw Markdown)

State is persisted in seen_jobs.json and committed back to the repo by the
GitHub Actions workflow so duplicate notifications are never sent.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, NamedTuple

import requests

# ---------------------------------------------------------------------------
# Configuration (injected via environment variables / GitHub Actions secrets)
# ---------------------------------------------------------------------------

TELEGRAM_TOKEN: str = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID: str = os.environ.get("CHAT_ID", "")

SEEN_JOBS_FILE: str = "seen_jobs.json"
API_HEALTH_FILE: str = "api_health.json"
BURST_SUMMARY_FILE: str = "burst_summary_2026-09-14.json"
MAX_INDIVIDUAL_ALERTS_PER_RUN = 15

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
        result = response.json()
        if not isinstance(result, dict) or result.get("ok") is not True:
            print("ERROR sending Telegram message: API did not confirm delivery.")
            return False
        return True
    except (requests.RequestException, ValueError) as exc:
        print(f"ERROR sending Telegram message: {exc}")
        return False


def format_job_message(job: dict[str, str]) -> str:
    """Return a clean, HTML-formatted Telegram message for a single job."""
    role = job.get("role", "Unknown Role")
    company = job.get("company", "Unknown Company")
    link = job.get("link", "#")
    emoji = job.get("emoji", "🆕")
    label = job.get("label", "Internship")
    return (
        f"{emoji} <b>{html.escape(role)}</b>\n"
        f"🏷 {html.escape(label)}\n"
        f"🏢 <i>{html.escape(company)}</i>\n"
        f'🔗 <a href="{html.escape(link, quote=True)}">Apply here</a>'
    )


def format_burst_summary(items: list[dict[str, Any]]) -> str:
    """One clickable Telegram block for the reviewed overnight placements."""
    lines = [
        "<b>Overnight industrial placements, reviewed shortlist</b>",
        f"{len(items)} placements from the 100 alerts sent on 14-15 Sep 2026 "
        "have confirmed opening dates and no past listed deadlines. "
        "Check the employer page before applying.",
        "",
    ]
    for item in items:
        opened = _trackr_date(item["openingDate"])
        closing = _trackr_date(item.get("closingDate"))
        opened_text = f"{opened.day} {opened:%b}"
        closing_text = f"closes {closing.day} {closing:%b}" if closing else "no deadline listed"
        label = html.escape(f'{item["company"]}, {item["role"]}')
        link = html.escape(item["url"], quote=True)
        lines.append(
            f'• Opened {opened_text}: <a href="{link}">{label}</a>, {closing_text}'
        )
    return "\n".join(lines)


def send_burst_summary() -> None:
    """Send the static, reviewed burst shortlist once, only on explicit dispatch."""
    with open(BURST_SUMMARY_FILE, "r", encoding="utf-8") as fh:
        state = json.load(fh)
    if state.get("sent_at"):
        print("Overnight shortlist was already sent; no Telegram message sent.")
        return

    items = state.get("items")
    if not isinstance(items, list) or len(items) != 19:
        raise RuntimeError("Overnight shortlist must contain the 19 reviewed placements")
    ids = [item["id"] for item in items]
    if len(set(ids)) != len(ids) or not set(ids).issubset(load_seen_jobs()):
        raise RuntimeError("Overnight shortlist IDs do not match the notified job state")

    today = datetime.now(timezone.utc).date()
    eligible = [item for item in items if _is_open_programme(item, today)]
    if not eligible:
        raise RuntimeError("No shortlist placements still pass the date check")
    message = format_burst_summary(eligible)
    visible_text = html.unescape(re.sub(r"<[^>]+>", "", message))
    if len(visible_text) > 4096:
        raise RuntimeError("Overnight shortlist exceeds Telegram's message limit")

    if not send_telegram_message(message):
        raise RuntimeError("Could not send overnight shortlist to Telegram")
    state["sent_at"] = datetime.now(timezone.utc).isoformat()
    with open(BURST_SUMMARY_FILE, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
        fh.write("\n")
    print(f"Sent one overnight shortlist containing {len(eligible)} placements.")


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
        "Jobert could not verify Trackr's API response. "
        "Job notifications are paused until the API check passes.\n\n"
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
        "Trackr's API check is passing again. "
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

# Trackr programmes API for all currently available UK Tech seasons. Add newly
# published seasons here as Trackr makes them available.
TRACKR_API_URL = "https://api.the-trackr.com/programmes"
TRACKR_SEASONS: tuple[str, ...] = ("2026", "2027", "2028")
TRACKR_PARAMS: dict[str, str] = {
    "region": "UK",
    "industry": "Tech",
}

# Scraping 4 programme types x 3 seasons means 12 requests per run instead of
# the original 3. A short delay between requests avoids bursting the API,
# which was observed to return soft-empty responses under rapid, back-to-back
# requests.
TRACKR_REQUEST_DELAY_SECONDS = 1.0
TRACKR_REQUEST_RETRIES = 2

# Keywords used to filter relevant opportunities. Only applied to programme
# types (below) where the "Tech" industry filter alone can still admit
# non-technical roles (e.g. a marketing internship at a tech company).
_ROLE_KEYWORDS = re.compile(
    r"intern|internship|spring\s*week|placement|co.?op|"
    r"software\s*eng|swe|ai|ml|machine\s*learning|quant",
    re.IGNORECASE,
)


class TrackrProgrammeType(NamedTuple):
    """One Trackr `type` query value and how to treat its results."""

    type: str
    label: str
    emoji: str
    filter_by_keyword: bool
    alert_on_empty: bool


# Every UK Tech programme category Jobert tracks. `filter_by_keyword` guards
# against non-technical roles slipping through under "Tech" industry; it's
# only meaningful for actual job/placement listings — spring week and event
# titles ("Launchpad Programme", "Discover Tech&AI") rarely contain those
# keywords even when genuinely relevant, so keyword-filtering them would
# wrongly discard almost everything. `alert_on_empty` is off for the newer,
# lower-volume categories since it's normal for them to have zero live
# listings for a future season — that's not an API breakage.
TRACKR_PROGRAMME_TYPES: tuple[TrackrProgrammeType, ...] = (
    TrackrProgrammeType(
        type="summer-internships",
        label="Internship",
        emoji="🆕",
        filter_by_keyword=True,
        alert_on_empty=True,
    ),
    TrackrProgrammeType(
        type="industrial-placements",
        label="Industrial Placement",
        emoji="🏗️",
        filter_by_keyword=True,
        alert_on_empty=False,
    ),
    TrackrProgrammeType(
        type="spring-weeks",
        label="Spring Week",
        emoji="🌱",
        filter_by_keyword=False,
        alert_on_empty=False,
    ),
    TrackrProgrammeType(
        type="events",
        label="Event",
        emoji="🎤",
        filter_by_keyword=False,
        alert_on_empty=False,
    ),
)


class TrackrApiError(RuntimeError):
    """Raised when Trackr is unavailable or breaks the expected API contract."""

    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__("Trackr API check failed: " + "; ".join(issues))


def _is_relevant(title: str) -> bool:
    return bool(_ROLE_KEYWORDS.search(title))


def _request_trackr_programmes(params: dict[str, str]) -> Any:
    """Retry a failed GET before treating a season as unavailable."""
    for attempt in range(TRACKR_REQUEST_RETRIES + 1):
        try:
            response = requests.get(
                TRACKR_API_URL,
                params=params,
                headers=HEADERS,
                timeout=(5, 20),
            )
            response.raise_for_status()
            return response.json()
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt == TRACKR_REQUEST_RETRIES:
                raise
            delay = 2 ** (attempt + 1)
            print(f"WARNING: Trackr request failed: {exc}; retrying in {delay}s.")
            time.sleep(delay)


def scrape_trackr() -> list[dict[str, str]]:
    """
    Fetch jobs for every configured season and programme type from the
    Trackr hidden JSON API (summer internships, industrial placements,
    spring weeks, and events — see TRACKR_PROGRAMME_TYPES).

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
        [{"id": str, "role": str, "company": str, "link": str, ...}, ...]
    """
    jobs: list[dict[str, str]] = []
    seen_job_ids: set[str] = set()
    issues: list[str] = []
    first_request = True

    for programme_type in TRACKR_PROGRAMME_TYPES:
        valid_responses = 0
        programme_count = 0

        for season in TRACKR_SEASONS:
            context = f"type {programme_type.type}, season {season}"
            if first_request:
                first_request = False
            else:
                time.sleep(TRACKR_REQUEST_DELAY_SECONDS)
            try:
                data: Any = _request_trackr_programmes(
                    {**TRACKR_PARAMS, "type": programme_type.type, "season": season}
                )
            except requests.RequestException as exc:
                issue = f"{context}: request failed: {exc}"
                print(f"WARNING: {issue}")
                issues.append(issue)
                continue
            except ValueError as exc:
                issue = f"{context}: response was not valid JSON: {exc}"
                print(f"WARNING: {issue}")
                issues.append(issue)
                continue

            programmes = _extract_programmes(data)
            if programmes is None:
                issue = (
                    f"{context}: expected a programmes list, received "
                    f"{_describe_response(data)}"
                )
                print(f"WARNING: {issue}")
                issues.append(issue)
                continue

            contract_issues = _programme_contract_issues(programmes, context)
            if contract_issues:
                for issue in contract_issues:
                    print(f"WARNING: {issue}")
                issues.extend(contract_issues)
                continue

            valid_responses += 1
            programme_count += len(programmes)

            found = 0
            for item in programmes:
                job = _normalise_trackr_job(item, programme_type)
                if job is None or job["id"] in seen_job_ids:
                    continue
                jobs.append(job)
                seen_job_ids.add(job["id"])
                found += 1
            print(f"Trackr {context}: found {found} relevant jobs.")

        if valid_responses == 0:
            issues.append(
                f"type {programme_type.type}: no configured season returned a "
                "usable programmes list"
            )
        elif programme_type.alert_on_empty and programme_count == 0:
            issues.append(
                f"type {programme_type.type}: all configured seasons returned "
                "empty programmes lists"
            )

    if issues:
        raise TrackrApiError(issues)

    print(f"Trackr: found {len(jobs)} relevant jobs across all seasons and types.")
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


def _programme_contract_issues(programmes: list[Any], context: str) -> list[str]:
    """Detect breaking changes to fields used by the normaliser."""
    if not programmes:
        return []
    records = [item for item in programmes if isinstance(item, dict)]
    if not records:
        return [f"{context}: programmes contains no object records"]

    required_fields = {
        "id": lambda item: bool(item.get("id")),
        "name or title": lambda item: bool(item.get("name") or item.get("title")),
        "company": lambda item: bool(item.get("company")),
        "openingDate": lambda item: "openingDate" in item,
    }
    missing = [
        field
        for field, is_present in required_fields.items()
        if not any(is_present(item) for item in records)
    ]
    if not missing:
        return []
    return [f"{context}: programme records have no usable {', '.join(missing)} field"]


def _normalise_trackr_job(
    item: Any, programme_type: TrackrProgrammeType
) -> dict[str, str] | None:
    """Validate and normalise one Trackr API programme."""
    if not isinstance(item, dict):
        return None
    if not _is_open_programme(item):
        return None

    role: str = str(item.get("name") or item.get("title") or "")

    if programme_type.filter_by_keyword:
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
        "opening_date": _trackr_date(item["openingDate"]).isoformat(),
        "label": programme_type.label,
        "emoji": programme_type.emoji,
    }


def _trackr_date(value: Any) -> date | None:
    """Read the calendar day from a Trackr ISO date without guessing missing dates."""
    if not isinstance(value, str) or not re.match(r"^\d{4}-\d{2}-\d{2}(?:T|$)", value):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _is_open_programme(item: dict[str, Any], today: date | None = None) -> bool:
    """Only advertise programmes with a confirmed opening and no elapsed deadline.

    Trackr includes historic and anticipated programmes alongside live ones. A
    reachable URL alone does not mean applications are accepting submissions.
    Closing dates are inclusive, so a programme closing today remains eligible.
    Without a deadline, an opening older than six months is too stale to trust.
    """
    today = today or datetime.now(timezone.utc).date()
    opening = _trackr_date(item.get("openingDate"))
    if opening is None or opening > today:
        return False

    closing_value = item.get("closingDate")
    if closing_value is not None:
        closing = _trackr_date(closing_value)
        if closing is None or closing < today:
            return False
    elif opening < today - timedelta(days=180):
        return False

    status = item.get("status")
    if status is not None and str(status).strip().lower() != "open":
        return False
    return True


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

    active_new_jobs.sort(key=lambda job: job["opening_date"], reverse=True)
    print(f"Total open, previously unsent jobs to notify: {len(active_new_jobs)}")

    newly_sent: list[str] = []
    # Individual emoji alerts are intentionally paced and capped so a category
    # backfill cannot flood the chat. The newest openings are sent first.
    for index, job in enumerate(active_new_jobs[:MAX_INDIVIDUAL_ALERTS_PER_RUN]):
        if index:
            time.sleep(2)
        success = send_telegram_message(format_job_message(job))
        if success:
            newly_sent.append(job["id"])
        print(f"  {'✓' if success else '✗'} Alert: {job['role']} @ {job['company']}")
    deferred = max(0, len(active_new_jobs) - MAX_INDIVIDUAL_ALERTS_PER_RUN)
    if deferred:
        print(f"Deferred {deferred} eligible jobs to the next scheduled run.")

    if newly_sent:
        seen.extend(newly_sent)
        save_seen_jobs(seen)
        print(f"State updated — {len(newly_sent)} new IDs saved.")
    else:
        print("No new jobs found or all notifications failed — state unchanged.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Jobert placement alerts")
    parser.add_argument("--send-burst-summary", action="store_true")
    args = parser.parse_args()
    if not TELEGRAM_TOKEN:
        print("ERROR: TELEGRAM_TOKEN environment variable is not set.")
        sys.exit(1)
    if not CHAT_ID:
        print("ERROR: CHAT_ID environment variable is not set.")
        sys.exit(1)
    if args.send_burst_summary:
        send_burst_summary()
    else:
        run()
