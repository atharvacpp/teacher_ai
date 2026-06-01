"""
main.py — FastAPI application shell for the ExplainAI backend (Phase 4).

This file contains only:
  • App initialisation
  • CORS middleware
  • Health-check endpoint
  • Router registration

All business logic lives in routers/ and services/.
"""

import asyncio
import io
import time
import wave
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from huggingface_hub import InferenceClient

from config import HF_API_KEY, ASR_MODEL_ID
from routers import chat, execute, upload, video, voice

# ---------------------------------------------------------------------------
# Background Tasks & Lifespan
# ---------------------------------------------------------------------------

def _generate_silent_wav_bytes() -> bytes:
    """Generate a 1-second silent WAV file entirely in memory."""
    buf = io.BytesIO()
    # 1 second of silence at 16000 Hz, 1 channel, 16-bit (2 bytes per sample)
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000)
    
    return buf.getvalue()


async def keep_model_awake():
    """Background loop to ping the HF distil-whisper endpoint every 3 mins."""
    print("[keep-alive] Starting distil-whisper keep-alive loop...")
    
    client = InferenceClient(
        api_key=HF_API_KEY, 
        headers={"Content-Type": "audio/wav"}
    )
    silent_audio_bytes = _generate_silent_wav_bytes()
    
    while True:
        start_time = time.perf_counter()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            # Run in a threadpool so we don't block the async event loop
            await asyncio.to_thread(
                client.automatic_speech_recognition,
                audio=silent_audio_bytes,
                model=ASR_MODEL_ID
            )
            duration = time.perf_counter() - start_time
            
            if duration < 2.0:
                print(f"[{timestamp}] \033[92m[Voice Monitor] Model is AWAKE (Ping time: {duration:.2f} seconds).\033[0m")
            elif duration > 5.0:
                print(f"[{timestamp}] \033[93m[Voice Monitor] WARNING: Model went to SLEEP (Ping time/Timeout: {duration:.2f} seconds).\033[0m")
            else:
                # Baseline intermediate state (2-5s)
                print(f"[{timestamp}] [Voice Monitor] Ping took {duration:.2f} seconds.")
                
        except Exception as e:
            duration = time.perf_counter() - start_time
            print(f"[{timestamp}] \033[91m[Voice Monitor] WARNING: Model went to SLEEP (Ping time/Timeout: {duration:.2f} seconds, Error: {e})\033[0m")
        
        # Pause for exactly 3 minutes
        await asyncio.sleep(180)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the FastAPI server."""
    # Startup
    keep_alive_task = asyncio.create_task(keep_model_awake())
    yield
    # Shutdown
    keep_alive_task.cancel()
    try:
        await keep_alive_task
    except asyncio.CancelledError:
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
app.include_router(execute.router)
app.include_router(upload.router)
app.include_router(video.router)
app.include_router(voice.router)
