"""
routers/voice.py — POST /transcribe endpoint.

Accepts an uploaded audio file, sends it to Distil-Whisper on
HuggingFace for automatic speech recognition, with automatic
retries for cold-starting models.
"""

import time

from fastapi import APIRouter, HTTPException, UploadFile, File
from huggingface_hub import InferenceClient

from config import HF_API_KEY, ASR_MODEL_ID, MAX_RETRIES, RETRY_DELAY_SECONDS

router = APIRouter(tags=["Voice"])


def _is_model_loading(error: Exception) -> bool:
    """Return True if the error indicates the HF model is still loading."""
    err = str(error).lower()
    return any(keyword in err for keyword in [
        "currently loading", "is currently loading",
        "model is loading", "service unavailable",
        "overloaded", "503",
    ])


@router.post("/transcribe")
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
        headers={"Content-Type": mime_type},
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
        error_detail = repr(last_exception)

    raise HTTPException(
        status_code=500,
        detail=error_detail,
    )
