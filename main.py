"""
main.py — FastAPI application shell for the ExplainAI backend (Phase 4).

This file contains only:
  • App initialisation
  • CORS middleware
  • Health-check endpoint
  • Router registration

All business logic lives in routers/ and services/.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import chat, upload, video, voice

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="ExplainAI Backend",
    description="Phase 4 backend powering the ExplainAI multimodal application.",
    version="0.4.0",
)

# ---------------------------------------------------------------------------
# CORS Middleware
# ---------------------------------------------------------------------------
# Allow the React dev server (various ports) to call our API without
# the browser blocking the request due to the same-origin policy.

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
        "http://localhost:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

@app.get("/ping")
def ping():
    return {"status": "ok", "version": "0.4.0"}

# ---------------------------------------------------------------------------
# Router Registration
# ---------------------------------------------------------------------------

app.include_router(chat.router)
app.include_router(upload.router)
app.include_router(video.router)
app.include_router(voice.router)
