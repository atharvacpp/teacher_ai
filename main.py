"""
main.py — FastAPI application shell for the ExplainAI backend (Phase 4).

This file contains only:
  • App initialisation
  • CORS middleware
  • Health-check endpoint
  • Router registration

All business logic lives in routers/ and services/.
"""

import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
import io
import time
import wave
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from huggingface_hub import InferenceClient

from config import HF_API_KEY, ASR_MODEL_ID
from routers import chat, pipeline_b_execution, pipeline_a_reasoning, video, voice, ws_execute, quiz, pipeline_c

# ---------------------------------------------------------------------------
# Background Tasks & Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the FastAPI server."""
    # Startup
    yield
    # Shutdown
    pass


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="ExplainAI Backend",
    description="Phase 5 backend with LangGraph code execution sandbox.",
    version="0.5.0",
    lifespan=lifespan,
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
app.include_router(pipeline_b_execution.router)
app.include_router(pipeline_a_reasoning.router)
app.include_router(video.router)
app.include_router(voice.router)
app.include_router(ws_execute.router)
app.include_router(quiz.router)
app.include_router(pipeline_c.router)
