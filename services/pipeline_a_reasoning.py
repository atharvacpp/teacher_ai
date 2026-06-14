"""
services/pipeline_a_reasoning.py — Multimodal Reasoning Pipeline

Graph:
START -> teacher -> reviewer -> END
"""

from typing import TypedDict
import asyncio
import json
from typing import AsyncGenerator

from huggingface_hub import InferenceClient
from langgraph.graph import StateGraph, START, END

from config import HF_API_KEY, CHAT_MODEL_ID
from services.tts import generate_tts_audio

REASONING_MODEL = "mistralai/Mistral-7B-Instruct-v0.3"

_hf_client = InferenceClient(api_key=HF_API_KEY)


class AgentStateA(TypedDict):
    """State for Pipeline A."""
    extracted_text: str
    user_prompt: str | None
    final_lesson: str


def _hf_reasoning_call(prompt: str, *, max_tokens: int = 2048) -> str:
    messages = [{"role": "user", "content": prompt}]
    print(f"[Reasoning | CLOUD] Calling {REASONING_MODEL} via HuggingFace ...")
    response = _hf_client.chat_completion(
        model=REASONING_MODEL,
        messages=messages,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


def teacher_node(state: AgentStateA) -> dict:
    """
    Node 1 — Teacher.
    Generate a polished markdown lesson from the extracted content.
    """
    print(f"[Teacher | CLOUD] Generating lesson via {REASONING_MODEL}")

    user_context = (
        f"\n\nThe student specifically asked: {state['user_prompt']}"
        if state.get("user_prompt")
        else ""
    )

    prompt = (
        "You are an expert teacher. Using ONLY the extracted content below, "
        "generate a highly readable, well-structured markdown lesson that "
        "explains all of the key concepts found in the document.\n\n"
        "IMPORTANT: Where appropriate, include a SHORT, self-contained, "
        "runnable Python code example inside a ```python fenced code block "
        "that demonstrates one of the core concepts. The code must print "
        "its output so it can be verified. Use clear headings, bullet points, "
        "and a logical teaching flow."
        f"{user_context}\n\n"
        f"--- Extracted Content ---\n{state['extracted_text']}"
    )

    lesson = _hf_reasoning_call(prompt, max_tokens=2048)
    return {"final_lesson": lesson}


def reviewer_node(state: AgentStateA) -> dict:
    """
    Node 2 - Reviewer.
    Pass-through node for future QA/Review logic.
    """
    print(f"[Reviewer] Lesson review complete.")
    return state


workflow_a = StateGraph(AgentStateA)
workflow_a.add_node("teacher", teacher_node)
workflow_a.add_node("reviewer", reviewer_node)

workflow_a.add_edge(START, "teacher")
workflow_a.add_edge("teacher", "reviewer")
workflow_a.add_edge("reviewer", END)
graph_a = workflow_a.compile()


async def stream_pipeline_a(
    extracted_text: str,
    user_prompt: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Run Pipeline A and yield SSE chunks for the frontend.
    Streams the lesson token-by-token, sends text_complete to unlock
    the UI, then generates TTS audio in a background thread.
    """

    yield f"data: {json.dumps({'type': 'log', 'message': 'Thinking...'})}\n\n"

    user_context = (
        f"\n\nThe student specifically asked: {user_prompt}"
        if user_prompt
        else ""
    )

    prompt = (
        "You are an expert teacher. Using ONLY the extracted content below, "
        "generate a highly readable, well-structured markdown lesson that "
        "explains all of the key concepts found in the document.\n\n"
        "IMPORTANT: Where appropriate, include a SHORT, self-contained, "
        "runnable Python code example inside a ```python fenced code block "
        "that demonstrates one of the core concepts. The code must print "
        "its output so it can be verified. Use clear headings, bullet points, "
        "and a logical teaching flow."
        f"{user_context}\n\n"
        f"--- Extracted Content ---\n{extracted_text}"
    )

    full_text = ""
    has_error = False
    try:
        from services.hf_chat import stream_chat_response
        for chunk in stream_chat_response(
            [{"role": "user", "content": prompt}], max_tokens=2048, model=REASONING_MODEL
        ):
            full_text += chunk
            yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
    except Exception as exc:
        has_error = True
        yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"

    # Signal text_complete so the frontend hides the Stop button immediately
    yield f"data: {json.dumps({'type': 'text_complete'})}\n\n"

    if has_error:
        return

    # TTS runs after text_complete — audio arrives as a late follow-up
    if full_text.strip():
        audio_base64 = None
        try:
            audio_base64 = await asyncio.to_thread(generate_tts_audio, full_text)
        except Exception as e:
            print(f"[Pipeline A] TTS error: {e}")

        if audio_base64:
            yield f"data: {json.dumps({'type': 'audio', 'audio_base64': audio_base64})}\n\n"
