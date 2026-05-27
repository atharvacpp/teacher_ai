"""
main.py — FastAPI backend for the ExplainAI multimodal web application (Phase 1).

This module sets up a single /chat endpoint that accepts the full conversation
history, forwards it to the Qwen/Qwen2.5-7B-Instruct model hosted on
Hugging Face, and returns the AI-generated explanation as JSON.
"""

import os
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
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
MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"

# Initialise the Hugging Face Inference Client with the API key
client = InferenceClient(api_key=HF_API_KEY)

# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="ExplainAI Backend",
    description="Phase 1 backend powering the ExplainAI multimodal application.",
    version="0.1.0",
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
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------------------------


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
            model=MODEL_ID,
            messages=messages,
            max_tokens=1024,
        )

        # Extract the assistant's reply from the response
        generated_text: str = completion.choices[0].message.content

        return ChatResponse(explanation=generated_text)

    except Exception as exc:
        # Surface a clean error to the client instead of a raw traceback
        raise HTTPException(
            status_code=502,
            detail=f"Hugging Face API error: {exc}",
        ) from exc
