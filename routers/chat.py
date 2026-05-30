"""
routers/chat.py — POST /chat endpoint.

Accepts the full conversation history, forwards it to the Qwen model
via HuggingFace, generates TTS audio, and returns both.
"""

from fastapi import APIRouter, HTTPException, Request

from schemas import ChatRequest, ChatResponse
from services.hf_chat import generate_chat_response
from services.tts import generate_tts_audio

router = APIRouter(tags=["Chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    """
    Accept the full conversation history, send it to the Qwen model via
    the Hugging Face Inference API, and return the generated explanation.
    """

    # Convert Pydantic models to plain dicts for the HF client
    messages = [{"role": m.role, "content": m.content} for m in body.messages]

    try:
        generated_text = generate_chat_response(messages)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Hugging Face API error: {exc}",
        ) from exc

    # Skip TTS if the client already disconnected
    audio_base64 = None
    if not await request.is_disconnected():
        audio_base64 = generate_tts_audio(generated_text)

    return ChatResponse(
        explanation=generated_text,
        audio_base64=audio_base64,
    )
