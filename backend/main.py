from fastapi import FastAPI
from .config import settings

app = FastAPI(title="Jobert AI Orchestrator")

@app.get("/")
async def root():
    return {"status": "online", "message": "Jobert AI Orchestrator is running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

# Phase 2 will add endpoints for /apply triggers and Notion population
