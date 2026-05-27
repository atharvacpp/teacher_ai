"""
main.py — FastAPI backend for the ExplainAI multimodal web application (Phase 2).

Endpoints:
  • /chat       – Accepts full conversation history, forwards to the Qwen model,
                  and returns the AI-generated explanation.
  • /transcribe – Accepts an uploaded audio file, sends it to Distil-Whisper
                  on Hugging Face for speech-to-text transcription.
"""

import base64
import io
import os
import time
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from huggingface_hub import InferenceClient
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Environment & Configuration
# ---------------------------------------------------------------------------

# Load environment variables from a local .env file (e.g. HUGGINGFACE_API_KEY)
load_dotenv()

# Retrieve the Hugging Face API key — never hardcoded
HF_API_KEY: str | None = os.getenv("HUGGINGFACE_API_KEY")
if not HF_API_KEY:
    raise RuntimeError(
        "HUGGINGFACE_API_KEY is not set. "
        "Please add it to your .env file before starting the server."
    )

# The specific model we target for chat completions
CHAT_MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"
ASR_MODEL_ID  = "openai/whisper-large-v3-turbo"

# Initialise the Hugging Face Inference Client with the API key
client = InferenceClient(api_key=HF_API_KEY)

# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="ExplainAI Backend",
    description="Phase 2 backend powering the ExplainAI multimodal application.",
    version="0.2.0",
)

# ---------------------------------------------------------------------------
# CORS Middleware
# ---------------------------------------------------------------------------
# Allow the React dev server (localhost:3000) to call our API without
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
# Request / Response Schemas
# ---------------------------------------------------------------------------

@app.get("/ping")
def ping():
    return {"status": "ok", "version": "new"}


class ChatMessage(BaseModel):
    """A single message in the conversation."""
    role: str
    content: str


class ChatRequest(BaseModel):
    """Schema for the incoming chat request payload."""
    messages: List[ChatMessage]


class ChatResponse(BaseModel):
    """Schema for the outgoing chat response payload."""
    explanation: str
    audio_base64: str | None = None


class TranscriptionResponse(BaseModel):
    """Schema for the outgoing transcription response payload."""
    transcription: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Accept the full conversation history, send it to the Qwen model via
    the Hugging Face Inference API, and return the generated explanation.
    """

    # Convert Pydantic models to plain dicts for the HF client
    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    try:
        # Call the Hugging Face Inference API for chat completions
        completion = client.chat.completions.create(
            model=CHAT_MODEL_ID,
            messages=messages,
            max_tokens=1024,
        )

        # Extract the assistant's reply from the response
        generated_text: str = completion.choices[0].message.content

        # Phase 2: Generate TTS for the AI's explanation
        audio_base64 = None
        try:
            from gtts import gTTS
            # We use gTTS to ensure 100% reliable, fast, free text-to-speech.
            tts = gTTS(text=generated_text, lang="en", slow=False)
            
            # Save the audio into an in-memory buffer
            fp = io.BytesIO()
            tts.write_to_fp(fp)
            fp.seek(0)
            
            # Encode those bytes into a Base64 string
            audio_base64 = base64.b64encode(fp.read()).decode("utf-8")
            
        except Exception as tts_exc:
            # If TTS fails, we log it but still return the text response
            print(f"[chat] TTS generation failed: {tts_exc}")
            raise tts_exc

        return ChatResponse(
            explanation=generated_text,
            audio_base64=audio_base64
        )

    except Exception as exc:
        # Surface a clean error to the client instead of a raw traceback
        raise HTTPException(
            status_code=502,
            detail=f"Hugging Face API error: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# POST /transcribe — Speech-to-Text via Distil-Whisper
# ---------------------------------------------------------------------------

# Retry settings for sleeping / cold-starting HF models
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5  # wait between retries (model usually wakes in 15-20s)


def _is_model_loading(error: Exception) -> bool:
    """Return True if the error indicates the HF model is still loading."""
    err = str(error).lower()
    return any(keyword in err for keyword in [
        "currently loading", "is currently loading",
        "model is loading", "service unavailable",
        "overloaded", "503",
    ])


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """
    Accept an uploaded audio file, send it to the distil-whisper/distil-large-v3
    model on Hugging Face for automatic speech recognition, and return the
    transcribed text.

    If the model is sleeping (cold start), the endpoint will automatically
    retry up to 3 times with a 5-second pause between attempts.

    Returns:
        200: {"transcription": "..."}
        500: {"detail": "..."}  — the raw error string from the HF API
    """

    # 1. Read the raw bytes from the uploaded file
    audio_bytes = await file.read()

    if not audio_bytes:
        raise HTTPException(
            status_code=500,
            detail="Uploaded audio file is empty.",
        )

    # 2. Attempt transcription with automatic retries for sleeping models
    last_exception: Exception | None = None
    
    # Hugging Face rejects raw bytes if no Content-Type is provided.
    # We instantiate a lightweight client here to attach the specific mime type.
    mime_type = file.content_type if file.content_type else "audio/webm"
    request_client = InferenceClient(
        api_key=HF_API_KEY,
        headers={"Content-Type": mime_type}
    )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = request_client.automatic_speech_recognition(
                audio=audio_bytes,
                model=ASR_MODEL_ID,
            )

            # Success — return the transcribed text
            transcribed_text: str = result.text  # type: ignore[union-attr]
            return {"transcription": transcribed_text}

        except Exception as e:
            last_exception = e

            if _is_model_loading(e) and attempt < MAX_RETRIES:
                # The model is waking up — wait and retry
                print(
                    f"[transcribe] Model is loading (attempt {attempt}/{MAX_RETRIES}). "
                    f"Retrying in {RETRY_DELAY_SECONDS}s…"
                )
                time.sleep(RETRY_DELAY_SECONDS)
                continue

            # Either it's NOT a loading error, or we've exhausted retries
            break

    # 3. All retries failed — forward the exact error to React
    error_detail = str(last_exception)
    if not error_detail.strip():
        # Some exceptions like StopIteration have an empty string representation
        error_detail = repr(last_exception)
        
    raise HTTPException(
        status_code=500,
        detail=error_detail,
    )

