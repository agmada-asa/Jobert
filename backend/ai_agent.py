"""Grounded application answer generation.

Jobert only calls Gemini when a user or server API key is configured. The
deterministic drafts created by the database remain available as a safe
fallback, so application preparation never depends on an external service.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from .config import settings
from .encryption import decrypt_string


async def generate_tailored_answers(
    user_data: dict[str, Any],
    job: dict[str, Any],
    questions: list[dict[str, Any]],
    cv_text: str,
) -> dict[str, str]:
    encrypted_key = user_data.get("gemini_api_key") or ""
    api_key = decrypt_string(encrypted_key) if encrypted_key else settings.GEMINI_API_KEY
    if not api_key:
        return {}

    profile = {
        "name": user_data.get("name"),
        "current_title": user_data.get("title"),
        "location": user_data.get("location"),
        "work_authorisation": user_data.get("work_authorisation"),
        "skills": json.loads(user_data.get("skills_json") or "[]"),
    }
    question_payload = [{"id": item["id"], "question": item["question"]} for item in questions]
    prompt = f"""
You are Jobert, a careful job-application assistant. Draft concise first-person
answers for the supplied questions. Use only facts present in the profile and
CV. Never invent employers, projects, dates, metrics, qualifications, or legal
status. If evidence is missing, write a short square-bracketed instruction for
the candidate to fill in. Tailor motivation to the job details without claiming
knowledge not shown below. Return one JSON object mapping each question id to
its answer, with no prose outside the JSON.

JOB:
{json.dumps({"role": job.get("role"), "company": job.get("company"), "location": job.get("location"), "summary": job.get("summary"), "categories": job.get("categories")}, ensure_ascii=False)}

PROFILE:
{json.dumps(profile, ensure_ascii=False)}

CV TEXT:
{cv_text[:24000] or "No CV text was available."}

QUESTIONS:
{json.dumps(question_payload, ensure_ascii=False)}
""".strip()

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.25},
    }
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(url, params={"key": api_key}, json=payload)
        response.raise_for_status()
        body = response.json()
    text = body["candidates"][0]["content"]["parts"][0]["text"]
    answers = json.loads(text)
    return {str(key): str(value) for key, value in answers.items() if isinstance(value, str)}
