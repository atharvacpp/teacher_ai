"""
routers/chat.py — POST /chat endpoint.

Accepts the full conversation history, forwards it to the Qwen model
via HuggingFace, generates TTS audio, and returns both.
"""

import asyncio
import json
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from schemas import ChatRequest
from services.hf_chat import stream_chat_response
from services.tts import generate_tts_audio

router = APIRouter(tags=["Chat"])

@router.post("/chat")
async def chat(request: Request, body: ChatRequest):
    """
    Accept the full conversation history, stream the Qwen model response via
    Server-Sent Events, signal text completion, then yield TTS audio on the
    same open connection while gTTS runs in a background thread.
    """

    # Convert Pydantic models to plain dicts for the HF client
    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    
    # Inject Teacher AI system prompt
    system_prompt = (
        "You are an enthusiastic, world-class expert tutor. Your goal is to "
        "explain complex topics so that they are incredibly fun, engaging, and easy to understand. "
        "Follow these rules:\n"
        "1. Hook the user: Start with a fascinating fact, a thought-provoking question, or an exciting opening.\n"
        "2. Use Analogies: Break down complex technical or abstract concepts using relatable, everyday analogies "
        "(e.g., comparing a computer processor to a chef in a kitchen).\n"
        "3. Tone: Be conversational, encouraging, and highly energetic. Never sound like a dry textbook or Wikipedia.\n"
        "4. Formatting: Use bold text for key terms, short paragraphs for readability, and pepper in relevant emojis "
        "to make the text visually pop.\n"
        "5. Check for Understanding: End your explanation with a light, encouraging question to keep the conversation flowing."
    )
    
    # Prepend the system prompt to the conversation history
    if not any(m["role"] == "system" for m in messages):
        messages.insert(0, {"role": "system", "content": system_prompt})

    async def event_stream():
        full_text = ""
        has_error = False
        try:
            for chunk in stream_chat_response(messages):
                if await request.is_disconnected():
                    break
                full_text += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
        except Exception as exc:
            has_error = True
            yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"

        if not has_error:
            yield f"data: {json.dumps({'type': 'text_complete'})}\n\n"

        if has_error or await request.is_disconnected():
            return

        if full_text.strip():
            audio_base64 = None
            try:
                audio_base64 = await asyncio.to_thread(generate_tts_audio, full_text)
            except Exception as e:
                print(f"[chat] TTS Generation error: {e}")

            if audio_base64 and not await request.is_disconnected():
                yield f"data: {json.dumps({'type': 'audio', 'data': audio_base64})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
