"""
routers/video.py — POST /youtube endpoint (Phase 4: Video Explainer).

Accepts a YouTube URL, fetches the video transcript via
youtube-transcript-api, concatenates it into a single text block,
and sends it to Qwen2.5 for a summarised explanation.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.hf_chat import generate_chat_response
from services.tts import generate_tts_audio

router = APIRouter(tags=["Video"])


# ---------------------------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------------------------

from schemas import YouTubeResponse

class YouTubeRequest(BaseModel):
    """Payload for the /youtube endpoint."""
    url: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Regex fallback for short-form URLs like youtu.be/VIDEO_ID
_SHORT_URL_RE = re.compile(
    r"(?:youtu\.be/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})"
)


def _extract_video_id(url: str) -> str:
    """
    Parse a YouTube URL and return the 11-character video ID.

    Supports:
      • https://www.youtube.com/watch?v=VIDEO_ID
      • https://youtu.be/VIDEO_ID
      • https://www.youtube.com/embed/VIDEO_ID
      • https://www.youtube.com/shorts/VIDEO_ID

    Raises:
        ValueError: If a video ID cannot be determined.
    """
    parsed = urlparse(url)

    # Standard: youtube.com/watch?v=...
    if "youtube.com" in (parsed.hostname or "") and parsed.path == "/watch":
        qs = parse_qs(parsed.query)
        vid = qs.get("v", [None])[0]
        if vid:
            return vid

    # Embed: youtube.com/embed/VIDEO_ID
    if "youtube.com" in (parsed.hostname or "") and parsed.path.startswith("/embed/"):
        segments = parsed.path.split("/")
        if len(segments) >= 3 and segments[2]:
            return segments[2]

    # Short URL / Shorts — regex approach
    match = _SHORT_URL_RE.search(url)
    if match:
        return match.group(1)

    raise ValueError(
        f"Could not extract a YouTube video ID from: {url}"
    )


# ---------------------------------------------------------------------------
# POST /youtube
# ---------------------------------------------------------------------------

@router.post("/youtube", response_model=YouTubeResponse)
async def process_youtube_video(body: YouTubeRequest):
    """
    Accept a YouTube URL, fetch its transcript, and return an AI-generated
    summary / explanation of the video content.
    """

    # 1. Extract the video ID from the user-supplied URL
    try:
        video_id = _extract_video_id(body.url.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    print(f"====== YOUTUBE TRANSCRIPT REQUEST ======")
    print(f"URL: {body.url}")
    print(f"Video ID: {video_id}")
    print(f"========================================")

    # 2. Fetch the transcript using youtube-transcript-api
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        transcript = YouTubeTranscriptApi().fetch(video_id)
    except Exception as exc:
        # Common failures: no transcript available, video is private, etc.
        print(f"[video] Transcript fetch failed: {exc}")
        raise HTTPException(
            status_code=502,
            detail=(
                f"Could not fetch transcript for video '{video_id}'. "
                "The video may not have captions, may be private, or "
                "the youtube-transcript-api may be blocked. "
                f"Error: {exc}"
            ),
        ) from exc

    # 3. Concatenate all transcript segments into one massive text block
    full_transcript = " ".join(
        snippet.text for snippet in transcript
    )

    if not full_transcript.strip():
        raise HTTPException(
            status_code=422,
            detail="Transcript was fetched but is empty (no spoken content detected).",
        )

    print(f"Transcript length: {len(full_transcript)} chars")
    print(f"Preview: {full_transcript[:300]}")
    print("=========================================")

    # 4. Stream the response to the frontend
    prompt = (
        "Summarize and explain the core concepts of this video transcript. "
        "Organise your response with clear headings, bullet points where "
        "appropriate, and provide any relevant context or insights:\n\n"
        f"{full_transcript}"
    )

    async def event_stream():
        import json
        from fastapi import Request
        # Note: We don't have Request in the signature, but we can just stream without disconnect check
        # Or let's just yield the chunks.
        
        # First, yield the transcript so the frontend can store it
        yield f"data: {json.dumps({'type': 'transcript', 'content': full_transcript})}\n\n"
        yield f"data: {json.dumps({'type': 'log', 'message': 'Thinking...'})}\n\n"

        full_text = ""
        has_error = False
        try:
            from services.hf_chat import stream_chat_response
            for chunk in stream_chat_response([{"role": "user", "content": prompt}], max_tokens=1024):
                full_text += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
        except Exception as exc:
            has_error = True
            yield f"data: {json.dumps({'type': 'error', 'content': f'LLM explanation error: {exc}'})}\n\n"

        # ALWAYS send 'text_complete' so the frontend hides "Thinking..." even after errors
        yield f"data: {json.dumps({'type': 'text_complete'})}\n\n"

        if has_error:
            return

        # TTS runs after — audio arrives as a late follow-up
        if full_text.strip():
            audio_base64 = None
            try:
                import asyncio
                audio_base64 = await asyncio.to_thread(generate_tts_audio, full_text)
            except Exception as e:
                print(f"TTS error: {e}")

            if audio_base64:
                yield f"data: {json.dumps({'type': 'audio', 'audio_base64': audio_base64})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# POST /video/upload (Local Video Uploads - Phase 4)
# ---------------------------------------------------------------------------

@router.post("/video/upload", response_model=YouTubeResponse)
async def upload_local_video(file: UploadFile = File(...)):
    """
    Accepts an uploaded local video file, extracts its audio using moviepy,
    transcribes it using faster-whisper locally, and then generates an explanation
    using Qwen2.5.
    """
    import os
    import tempfile
    from fastapi import UploadFile
    from services.asr import transcribe_audio

    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(
            status_code=400, detail="Invalid file type. Please upload a video."
        )

    print(f"====== LOCAL VIDEO UPLOAD REQUEST ======")
    print(f"File Name: {file.filename}")
    print(f"Content Type: {file.content_type}")
    print("========================================")

    # 1. Save uploaded video to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp_video:
        video_bytes = await file.read()
        tmp_video.write(video_bytes)
        tmp_video_path = tmp_video.name

    tmp_audio_path = tmp_video_path.replace(".mp4", ".wav")
    transcript_text = ""

    try:
        # 2. Extract audio using moviepy
        from moviepy import VideoFileClip
        print("[video] Extracting audio track via moviepy...")
        with VideoFileClip(tmp_video_path) as clip:
            if clip.audio is None:
                raise HTTPException(
                    status_code=422,
                    detail="No audio track found in the uploaded video."
                )
            clip.audio.write_audiofile(tmp_audio_path, logger=None)

        # 3. Read the extracted audio bytes
        with open(tmp_audio_path, "rb") as af:
            audio_bytes = af.read()

        # 4. Transcribe using faster-whisper locally
        print("[video] Transcribing audio via faster-whisper...")
        try:
            transcript_text = transcribe_audio(audio_bytes)
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"Audio transcription failed: {str(e)}"
            )

        if not transcript_text:
            raise HTTPException(
                status_code=502,
                detail="Audio transcription failed: No text returned."
            )

        print(f"Transcript length: {len(transcript_text)} chars")
        print(f"Preview: {transcript_text[:300]}")
        print("========================================")

    finally:
        # Cleanup temporary files
        try:
            if os.path.exists(tmp_video_path):
                os.remove(tmp_video_path)
            if os.path.exists(tmp_audio_path):
                os.remove(tmp_audio_path)
        except Exception as e:
            print(f"[video] Warning: could not clean up temp files: {e}")

        # 3. Stream the response to the frontend
        prompt = (
            "Summarize and explain the core concepts of this video transcript. "
            "Organise your response with clear headings, bullet points where "
            "appropriate, and provide any relevant context or insights:\n\n"
            f"{transcript_text}"
        )

        async def event_stream():
            import json
            yield f"data: {json.dumps({'type': 'transcript', 'content': transcript_text})}\n\n"
            yield f"data: {json.dumps({'type': 'log', 'message': 'Thinking...'})}\n\n"

            full_text = ""
            has_error = False
            try:
                from services.hf_chat import stream_chat_response
                for chunk in stream_chat_response([{"role": "user", "content": prompt}], max_tokens=1024):
                    full_text += chunk
                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
            except Exception as exc:
                has_error = True
                yield f"data: {json.dumps({'type': 'error', 'content': f'LLM explanation error: {exc}'})}\n\n"

            # ALWAYS send 'text_complete' so the frontend hides "Thinking..." even after errors
            yield f"data: {json.dumps({'type': 'text_complete'})}\n\n"

            if has_error:
                return

            # TTS runs after — audio arrives as a late follow-up
            if full_text.strip():
                audio_base64 = None
                try:
                    import asyncio
                    from services.tts import generate_tts_audio
                    audio_base64 = await asyncio.to_thread(generate_tts_audio, full_text)
                except Exception as e:
                    print(f"TTS error: {e}")

                if audio_base64:
                    yield f"data: {json.dumps({'type': 'audio', 'audio_base64': audio_base64})}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")
