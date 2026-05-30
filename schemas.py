"""
schemas.py — Pydantic request/response models shared across routers.
"""

from typing import List

from pydantic import BaseModel


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
