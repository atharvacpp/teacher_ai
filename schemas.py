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


class YouTubeResponse(BaseModel):
    """Response from the /youtube endpoint."""
    explanation: str
    transcript: str
    audio_base64: str | None = None


class ChatResponse(BaseModel):
    """Schema for the outgoing chat response payload."""
    explanation: str
    audio_base64: str | None = None


class TranscriptionResponse(BaseModel):
    """Schema for the outgoing transcription response payload."""
    transcription: str


# ---------------------------------------------------------------------------
# Quiz Schemas (Focus Mode)
# ---------------------------------------------------------------------------

class QuizQuestion(BaseModel):
    """A single multiple-choice question for Focus Mode quizzes."""
    question_text: str
    options: List[str]               # Exactly 4 options
    correct_answer: str              # The full text of the correct option
    explanation_if_wrong: str        # Explanation shown when the user picks wrong

class QuizSchema(BaseModel):
    """Full quiz structure returned by the AI."""
    quiz_title: str
    questions: List[QuizQuestion]

class GenerateQuizRequest(BaseModel):
    """Payload for the /api/generate-quiz endpoint."""
    video_id: str
    video_title: str
    video_transcript: str

class GenerateQuizResponse(BaseModel):
    """Response from the /api/generate-quiz endpoint."""
    quiz: QuizSchema

