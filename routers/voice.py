"""
routers/voice.py — POST /transcribe endpoint.

Accepts an uploaded audio file, transcribes it locally using faster-whisper.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File
from services.asr import transcribe_audio

router = APIRouter(tags=["Voice"])

@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """
    Accept an uploaded audio file, transcribe it using faster-whisper locally,
    and return the transcribed text.

    Returns:
        200: {"transcription": "..."}
        500: {"detail": "..."}
    """

    # 1. Read the raw bytes from the uploaded file
    audio_bytes = await file.read()

    if not audio_bytes:
        raise HTTPException(
            status_code=500,
            detail="Uploaded audio file is empty.",
        )

    # 2. Attempt local transcription
    try:
        transcribed_text = transcribe_audio(audio_bytes)
        return {"transcription": transcribed_text}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Local ASR failed: {str(e)}",
        )
