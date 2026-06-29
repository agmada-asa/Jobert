"""Persistent storage for the Jobert web application.

SQLite is the default store so the product works without a provisioned cloud
project. All queries are scoped by the authenticated user's id. The module also
keeps the small compatibility surface used by the legacy Telegram bot.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from .config import settings
from .encryption import encrypt_string


DATABASE_PATH = Path(settings.DATABASE_PATH)
UPLOAD_DIR = Path(settings.UPLOAD_DIR)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_database() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                location TEXT NOT NULL DEFAULT '',
                work_authorisation TEXT NOT NULL DEFAULT '',
                skills_json TEXT NOT NULL DEFAULT '[]',
                gemini_api_key TEXT,
                telegram_id INTEGER UNIQUE,
                notion_token TEXT,
                notion_kb_page_id TEXT,
                cv_url TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cvs (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                text_content TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                is_current INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT NOT NULL DEFAULT 'United Kingdom',
                link TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'trackr',
                season TEXT,
                categories_json TEXT NOT NULL DEFAULT '[]',
                closing_date TEXT,
                first_seen_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS saved_jobs (
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                saved_at TEXT NOT NULL,
                PRIMARY KEY (user_id, job_id)
            );

            CREATE TABLE IF NOT EXISTS applications (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                status TEXT NOT NULL DEFAULT 'In progress',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, job_id)
            );

            CREATE TABLE IF NOT EXISTS application_answers (
                id TEXT PRIMARY KEY,
                application_id TEXT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
                question TEXT NOT NULL,
                value TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'review',
                source TEXT NOT NULL DEFAULT 'Profile',
                position INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_updated ON jobs(updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_applications_user ON applications(user_id, updated_at DESC);
            """
        )
        user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "cv_url" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN cv_url TEXT")


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000)
    return f"pbkdf2_sha256$240000${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        _, iterations, salt_hex, expected = encoded.split("$", 3)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        ).hex()
        return hmac.compare_digest(digest, expected)
    except (TypeError, ValueError):
        return False


def create_web_user(email: str, password: str, name: str) -> dict[str, Any]:
    timestamp = now_iso()
    user_id = str(uuid.uuid4())
    try:
        with connection() as conn:
            conn.execute(
                """INSERT INTO users
                (id, email, password_hash, name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, email.strip().lower(), hash_password(password), name.strip(), timestamp, timestamp),
            )
    except sqlite3.IntegrityError as exc:
        raise ValueError("An account already exists for this email") from exc
    return get_web_user(user_id) or {}


def authenticate(email: str, password: str) -> dict[str, Any] | None:
    with connection() as conn:
        user = _row(conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone())
    return user if user and verify_password(password, user["password_hash"]) else None


def create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    created = datetime.now(UTC)
    expires = created + timedelta(days=settings.SESSION_DAYS)
    with connection() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (created.isoformat(),))
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (token_hash, user_id, expires.isoformat(), created.isoformat()),
        )
    return token


def user_for_token(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with connection() as conn:
        return _row(
            conn.execute(
                """SELECT users.* FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = ? AND sessions.expires_at > ?""",
                (token_hash, now_iso()),
            ).fetchone()
        )


def delete_session(token: str) -> None:
    with connection() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (hashlib.sha256(token.encode()).hexdigest(),))


def get_web_user(user_id: str) -> dict[str, Any] | None:
    with connection() as conn:
        return _row(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def serialize_profile(user: dict[str, Any]) -> dict[str, Any]:
    current_cv = get_current_cv(user["id"])
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "title": user.get("title") or "",
        "location": user.get("location") or "",
        "workAuthorisation": user.get("work_authorisation") or "",
        "skills": json.loads(user.get("skills_json") or "[]"),
        "cv": ({"id": current_cv["id"], "filename": current_cv["filename"], "uploadedAt": current_cv["created_at"]} if current_cv else None),
        "aiConfigured": bool(user.get("gemini_api_key") or settings.GEMINI_API_KEY),
    }


def update_profile(user_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "name": "name",
        "title": "title",
        "location": "location",
        "workAuthorisation": "work_authorisation",
        "skills": "skills_json",
        "geminiApiKey": "gemini_api_key",
    }
    assignments: list[str] = []
    values: list[Any] = []
    for key, column in allowed.items():
        if key not in fields:
            continue
        value = fields[key]
        if key == "skills":
            value = json.dumps([str(item).strip() for item in value if str(item).strip()])
        elif key == "geminiApiKey":
            if not value:
                continue
            value = encrypt_string(str(value).strip())
        assignments.append(f"{column} = ?")
        values.append(value)
    if assignments:
        assignments.append("updated_at = ?")
        values.extend([now_iso(), user_id])
        with connection() as conn:
            conn.execute(f"UPDATE users SET {', '.join(assignments)} WHERE id = ?", values)
    user = get_web_user(user_id)
    return serialize_profile(user or {})


def save_cv(user_id: str, filename: str, source: Any, text_content: str = "") -> dict[str, Any]:
    safe_name = Path(filename).name.replace("\x00", "") or "cv.pdf"
    cv_id = str(uuid.uuid4())
    user_dir = UPLOAD_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    destination = user_dir / f"{cv_id}.pdf"
    content_hash = hashlib.sha256()
    with destination.open("wb") as target:
        while chunk := source.read(1024 * 1024):
            content_hash.update(chunk)
            target.write(chunk)
    with connection() as conn:
        conn.execute("UPDATE cvs SET is_current = 0 WHERE user_id = ?", (user_id,))
        conn.execute(
            """INSERT INTO cvs
            (id, user_id, filename, stored_path, content_hash, text_content, created_at, is_current)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            (cv_id, user_id, safe_name, str(destination), content_hash.hexdigest(), text_content, now_iso()),
        )
    return get_current_cv(user_id) or {}


def get_current_cv(user_id: str) -> dict[str, Any] | None:
    with connection() as conn:
        return _row(conn.execute("SELECT * FROM cvs WHERE user_id = ? AND is_current = 1", (user_id,)).fetchone())


def import_jobs(records: list[dict[str, Any]]) -> int:
    if not records:
        return 0
    timestamp = now_iso()
    with connection() as conn:
        for job in records:
            job_id = str(job.get("id") or "").strip()
            if not job_id:
                continue
            locations = job.get("locations") or []
            location = job.get("location") or (", ".join(locations) if isinstance(locations, list) else str(locations)) or "United Kingdom"
            company_description = job.get("company_description") or ""
            summary = job.get("summary") or company_description
            conn.execute(
                """INSERT INTO jobs
                (id, role, company, location, link, summary, source, season, categories_json,
                 closing_date, first_seen_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    role=excluded.role, company=excluded.company, location=excluded.location,
                    link=excluded.link, summary=excluded.summary, source=excluded.source,
                    season=excluded.season, categories_json=excluded.categories_json,
                    closing_date=excluded.closing_date, updated_at=excluded.updated_at""",
                (
                    job_id,
                    job.get("role") or "Unknown role",
                    job.get("company") or "Unknown company",
                    location,
                    job.get("link") or "",
                    summary[:1000],
                    job.get("source") or "trackr",
                    str(job.get("season") or ""),
                    json.dumps(job.get("categories") or []),
                    job.get("closing_date"),
                    job.get("first_seen_at") or timestamp,
                    timestamp,
                ),
            )
    return len(records)


def import_jobs_file(path: str | Path | None = None) -> int:
    source = Path(path or settings.JOBS_FILE)
    if not source.exists():
        return 0
    try:
        records = json.loads(source.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    return import_jobs(records if isinstance(records, list) else [])


def _match_score(profile: dict[str, Any], job: dict[str, Any]) -> int:
    skills = [item.lower() for item in profile.get("skills", [])]
    haystack = f"{job.get('role', '')} {job.get('summary', '')} {' '.join(job.get('categories', []))}".lower()
    matches = sum(1 for skill in skills if skill in haystack)
    return min(97, 62 + matches * 7) if skills else 70


def list_jobs(user_id: str, limit: int = 1000, query: str = "") -> list[dict[str, Any]]:
    user = get_web_user(user_id)
    profile = serialize_profile(user or {})
    params: list[Any] = [user_id]
    where = ""
    if query.strip():
        where = "WHERE jobs.role LIKE ? OR jobs.company LIKE ?"
        value = f"%{query.strip()}%"
        params.extend([value, value])
    params.append(limit)
    with connection() as conn:
        rows = conn.execute(
            f"""SELECT jobs.*, saved_jobs.saved_at,
            applications.id AS application_id, applications.status AS application_status
            FROM jobs
            LEFT JOIN saved_jobs ON saved_jobs.job_id = jobs.id AND saved_jobs.user_id = ?
            LEFT JOIN applications ON applications.job_id = jobs.id AND applications.user_id = ?
            {where}
            ORDER BY jobs.updated_at DESC, jobs.company, jobs.role LIMIT ?""",
            [user_id, *params],
        ).fetchall()
    result = []
    for row in rows:
        job = dict(row)
        job["categories"] = json.loads(job.pop("categories_json") or "[]")
        job["saved"] = bool(job.pop("saved_at"))
        job["match"] = _match_score(profile, job)
        result.append(job)
    return result


def set_job_saved(user_id: str, job_id: str, saved: bool) -> None:
    with connection() as conn:
        if saved:
            conn.execute(
                "INSERT OR IGNORE INTO saved_jobs (user_id, job_id, saved_at) VALUES (?, ?, ?)",
                (user_id, job_id, now_iso()),
            )
        else:
            conn.execute("DELETE FROM saved_jobs WHERE user_id = ? AND job_id = ?", (user_id, job_id))


def _application_answers(conn: sqlite3.Connection, application_id: str) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(
        "SELECT * FROM application_answers WHERE application_id = ? ORDER BY position", (application_id,)
    ).fetchall()]


def list_applications(user_id: str) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """SELECT applications.*, jobs.role, jobs.company, jobs.location, jobs.link
            FROM applications JOIN jobs ON jobs.id = applications.job_id
            WHERE applications.user_id = ? ORDER BY applications.updated_at DESC""",
            (user_id,),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["answers"] = _application_answers(conn, item["id"])
            result.append(item)
        return result


def _draft_answers(profile: dict[str, Any], cv_text: str, job: dict[str, Any]) -> list[dict[str, str]]:
    name = profile.get("name") or "the candidate"
    title = profile.get("title") or "candidate"
    skills = profile.get("skills") or []
    top_skills = ", ".join(skills[:4]) or "the skills described in my CV"
    work_auth = profile.get("workAuthorisation") or "Please review and add your work authorisation details."
    cv_source = "CV + profile" if cv_text.strip() else "Profile"
    return [
        {
            "question": "Tell us about yourself.",
            "value": f"I’m {name}, a {title} with experience across {top_skills}. I enjoy turning complex problems into clear, reliable solutions and working closely with teams to deliver useful outcomes.",
            "source": cv_source,
        },
        {
            "question": f"Why do you want to work at {job['company']}?",
            "value": f"I’m interested in {job['company']} because this {job['role']} opportunity aligns with my experience in {top_skills}. I’d welcome the chance to learn from the team, contribute thoughtfully, and build work that has a meaningful impact.",
            "source": "Job description + profile",
        },
        {
            "question": "Describe relevant experience or a challenging problem you solved.",
            "value": "Use a specific example from your CV: explain the situation, the action you took, the result, and what you learned. Add a measurable result before accepting this answer.",
            "source": cv_source,
        },
        {
            "question": "Do you have the right to work in the UK?",
            "value": work_auth,
            "source": "Profile · Work authorisation",
        },
    ]


def prepare_application(user_id: str, job_id: str) -> dict[str, Any]:
    with connection() as conn:
        existing = conn.execute(
            "SELECT id FROM applications WHERE user_id = ? AND job_id = ?", (user_id, job_id)
        ).fetchone()
        if existing:
            app_id = existing["id"]
        else:
            job = _row(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())
            if not job:
                raise ValueError("Job not found")
            app_id = str(uuid.uuid4())
            timestamp = now_iso()
            conn.execute(
                "INSERT INTO applications (id, user_id, job_id, status, created_at, updated_at) VALUES (?, ?, ?, 'In progress', ?, ?)",
                (app_id, user_id, job_id, timestamp, timestamp),
            )
            user = _row(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()) or {}
            profile = serialize_profile(user)
            cv = _row(conn.execute("SELECT * FROM cvs WHERE user_id = ? AND is_current = 1", (user_id,)).fetchone())
            for position, draft in enumerate(_draft_answers(profile, (cv or {}).get("text_content", ""), job)):
                conn.execute(
                    """INSERT INTO application_answers
                    (id, application_id, question, value, status, source, position)
                    VALUES (?, ?, ?, ?, 'review', ?, ?)""",
                    (str(uuid.uuid4()), app_id, draft["question"], draft["value"], draft["source"], position),
                )
            conn.execute(
                "INSERT OR IGNORE INTO saved_jobs (user_id, job_id, saved_at) VALUES (?, ?, ?)",
                (user_id, job_id, timestamp),
            )
    return next(app for app in list_applications(user_id) if app["id"] == app_id)


def application_generation_context(user_id: str, application_id: str) -> tuple[dict[str, Any], dict[str, Any], str, list[dict[str, Any]]]:
    with connection() as conn:
        user = _row(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()) or {}
        job = _row(conn.execute(
            """SELECT jobs.* FROM jobs JOIN applications ON applications.job_id = jobs.id
            WHERE applications.id = ? AND applications.user_id = ?""",
            (application_id, user_id),
        ).fetchone()) or {}
        if job:
            job["categories"] = json.loads(job.pop("categories_json") or "[]")
        cv = _row(conn.execute("SELECT * FROM cvs WHERE user_id = ? AND is_current = 1", (user_id,)).fetchone()) or {}
        answers = _application_answers(conn, application_id)
    return user, job, cv.get("text_content", ""), answers


def update_answer(user_id: str, application_id: str, answer_id: str, value: str | None, status: str | None) -> None:
    assignments: list[str] = []
    assignment_values: list[Any] = []
    if value is not None:
        assignments.append("value = ?")
        assignment_values.append(value)
    if status is not None:
        assignments.append("status = ?")
        assignment_values.append(status)
    if not assignments:
        return
    with connection() as conn:
        cursor = conn.execute(
            f"""UPDATE application_answers SET {', '.join(assignments)}
            WHERE id = ? AND application_id = ? AND EXISTS (
                SELECT 1 FROM applications WHERE id = ? AND user_id = ?
            )""",
            [*assignment_values, answer_id, application_id, application_id, user_id],
        )
        if cursor.rowcount == 0:
            raise ValueError("Answer not found")
        conn.execute("UPDATE applications SET updated_at = ? WHERE id = ?", (now_iso(), application_id))


def update_application_status(user_id: str, application_id: str, status: str) -> None:
    with connection() as conn:
        cursor = conn.execute(
            "UPDATE applications SET status = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (status, now_iso(), application_id, user_id),
        )
        if cursor.rowcount == 0:
            raise ValueError("Application not found")


# Legacy Telegram compatibility -------------------------------------------------


def get_user(telegram_id: int) -> dict[str, Any] | None:
    with connection() as conn:
        return _row(conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone())


def create_or_update_user(telegram_id: int, **kwargs: Any) -> dict[str, Any]:
    user = get_user(telegram_id)
    timestamp = now_iso()
    if user:
        columns = ", ".join(f"{key} = ?" for key in kwargs)
        with connection() as conn:
            conn.execute(f"UPDATE users SET {columns}, updated_at = ? WHERE telegram_id = ?", [*kwargs.values(), timestamp, telegram_id])
    else:
        with connection() as conn:
            conn.execute(
                """INSERT INTO users
                (id, email, password_hash, name, telegram_id, created_at, updated_at, notion_token, gemini_api_key, notion_kb_page_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()), f"telegram-{telegram_id}@local.jobert", hash_password(secrets.token_urlsafe()),
                    f"Telegram user {telegram_id}", telegram_id, timestamp, timestamp,
                    kwargs.get("notion_token"), kwargs.get("gemini_api_key"), kwargs.get("notion_kb_page_id"),
                ),
            )
    return get_user(telegram_id) or {}


def upload_cv(telegram_id: int, file_content: bytes, filename: str) -> str:
    user = get_user(telegram_id)
    if not user:
        user = create_or_update_user(telegram_id)
    from io import BytesIO

    cv = save_cv(user["id"], filename, BytesIO(file_content))
    return cv["stored_path"]


init_database()
