from __future__ import annotations

import io
import logging
from contextlib import asynccontextmanager
from typing import Any

import PyPDF2
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

from . import database
from .ai_agent import generate_tailored_answers


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.init_database()
    imported = database.import_jobs_file()
    logger.info("Imported %s jobs from the catalog", imported)
    yield


app = FastAPI(title="Jobert API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class Registration(Credentials):
    name: str = Field(min_length=2, max_length=120)


class ProfileUpdate(BaseModel):
    name: str | None = None
    title: str | None = None
    location: str | None = None
    workAuthorisation: str | None = None
    skills: list[str] | None = None
    geminiApiKey: str | None = None


class SavedUpdate(BaseModel):
    saved: bool


class ApplicationCreate(BaseModel):
    jobId: str


class AnswerUpdate(BaseModel):
    value: str | None = None
    status: str | None = Field(default=None, pattern="^(review|accepted)$")


class StatusUpdate(BaseModel):
    status: str = Field(pattern="^(In progress|Ready to submit|Submitted|Under review|Offer|Rejected)$")


def _token(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Sign in required")
    return authorization.removeprefix("Bearer ").strip()


def current_user(token: str = Depends(_token)) -> dict[str, Any]:
    user = database.user_for_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Your session has expired")
    return user


def auth_response(user: dict[str, Any]) -> dict[str, Any]:
    return {"token": database.create_session(user["id"]), "profile": database.serialize_profile(user)}


def bootstrap(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile": database.serialize_profile(user),
        "jobs": database.list_jobs(user["id"]),
        "applications": database.list_applications(user["id"]),
    }


@app.get("/")
async def root():
    return {"status": "online", "message": "Jobert API is running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/auth/register", status_code=201)
async def register(payload: Registration):
    try:
        user = database.create_web_user(payload.email, payload.password, payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return auth_response(user)


@app.post("/auth/login")
async def login(payload: Credentials):
    user = database.authenticate(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    return auth_response(user)


@app.post("/auth/logout", status_code=204)
async def logout(token: str = Depends(_token)):
    database.delete_session(token)


@app.get("/bootstrap")
async def get_bootstrap(user: dict[str, Any] = Depends(current_user)):
    return bootstrap(user)


@app.patch("/profile")
async def patch_profile(payload: ProfileUpdate, user: dict[str, Any] = Depends(current_user)):
    return database.update_profile(user["id"], payload.model_dump(exclude_unset=True))


@app.post("/profile/cv")
async def upload_cv(file: UploadFile = File(...), user: dict[str, Any] = Depends(current_user)):
    if file.content_type != "application/pdf" and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Please upload a PDF CV")
    content = await file.read()
    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=415, detail="The uploaded file is not a valid PDF")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="CV must be smaller than 10 MB")
    text = ""
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        logger.info("Uploaded CV could not be text-extracted", exc_info=True)
    cv = database.save_cv(user["id"], file.filename, io.BytesIO(content), text)
    return {"id": cv["id"], "filename": cv["filename"], "uploadedAt": cv["created_at"]}


@app.get("/jobs")
async def jobs(
    query: str = Query(default="", max_length=100),
    user: dict[str, Any] = Depends(current_user),
):
    return database.list_jobs(user["id"], query=query)


@app.patch("/jobs/{job_id}/saved", status_code=204)
async def save_job(job_id: str, payload: SavedUpdate, user: dict[str, Any] = Depends(current_user)):
    database.set_job_saved(user["id"], job_id, payload.saved)


@app.post("/applications", status_code=201)
async def create_application(payload: ApplicationCreate, user: dict[str, Any] = Depends(current_user)):
    try:
        application = database.prepare_application(user["id"], payload.jobId)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if user.get("gemini_api_key") or database.settings.GEMINI_API_KEY:
        try:
            user_data, job, cv_text, questions = database.application_generation_context(user["id"], application["id"])
            generated = await generate_tailored_answers(user_data, job, questions, cv_text)
            for answer in questions:
                value = generated.get(answer["id"])
                if value:
                    database.update_answer(user["id"], application["id"], answer["id"], value, "review")
            application = next(item for item in database.list_applications(user["id"]) if item["id"] == application["id"])
        except Exception:
            logger.warning("AI drafting failed; returning grounded fallback drafts", exc_info=True)
    return application


@app.patch("/applications/{application_id}/answers/{answer_id}", status_code=204)
async def patch_answer(
    application_id: str,
    answer_id: str,
    payload: AnswerUpdate,
    user: dict[str, Any] = Depends(current_user),
):
    try:
        database.update_answer(user["id"], application_id, answer_id, payload.value, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.patch("/applications/{application_id}/status", status_code=204)
async def patch_application_status(
    application_id: str,
    payload: StatusUpdate,
    user: dict[str, Any] = Depends(current_user),
):
    try:
        database.update_application_status(user["id"], application_id, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
