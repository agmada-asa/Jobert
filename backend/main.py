from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Any
from .config import settings
from .database import get_user, create_or_update_user
from .encryption import decrypt_string
from .ai_agent import generate_tailored_answers
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Jobert AI Orchestrator")

# Catch validation errors to debug 422s
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    body = await request.body()
    logger.error(f"Validation Error: {exc.errors()}\nBody: {body.decode()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": body.decode()},
    )

# Enable CORS for the Chrome extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AuthRequest(BaseModel):
    code: str

class ApplicationCreate(BaseModel):
    job_url: str
    company_name: str
    role_title: str
    status: str = "Draft"

@app.get("/")
async def root():
    return {"status": "online", "message": "Jobert AI Orchestrator is running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.post("/extension/auth-verify")
async def verify_extension_code(auth: AuthRequest):
    if auth.code == "123456":
        # Using the actual user ID found in the database for demo purposes: 8687167751
        return {"token": "mock_access_token_abc123", "user_id": 8687167751}
    raise HTTPException(status_code=401, detail="Invalid magic code")

@app.get("/user/profile")
async def get_user_profile(user_id: int):
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "cv_url": user.get("cv_url"),
        "notion_kb_page_id": user.get("notion_kb_page_id"),
        "has_gemini_key": bool(user.get("gemini_api_key"))
    }

class GenerateRequest(BaseModel):
    user_id: Any
    job_url: str
    questions: List[dict]

@app.post("/generate-answers")
async def generate_answers(req: GenerateRequest):
    logger.info(f"Received generate-answers request for user_id: {req.user_id}")
    
    try:
        user_id_int = int(req.user_id)
    except:
        raise HTTPException(status_code=400, detail="user_id must be an integer")

    user = get_user(user_id_int)
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id_int} not found.")
    
    try:
        answers = await generate_tailored_answers(user, req.job_url, req.questions)
        return {"answers": answers}
    except Exception as e:
        logger.error(f"AI Generation Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/applications")
async def save_application(app_data: ApplicationCreate, user_id: int):
    return {"status": "success", "message": "Application saved"}
