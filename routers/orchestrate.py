"""
routers/orchestrate.py — POST /api/orchestrate endpoint for Magic Wand debugging.

Streams LangGraph progress as Server-Sent Events (SSE) back to the frontend.
"""

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.orchestrator import stream_magic_wand

router = APIRouter(tags=["Orchestrate"])

class OrchestrateRequest(BaseModel):
    code: str
    language: str
    terminal_error: str | None = None

@router.post("/api/orchestrate")
async def orchestrate_debug(request: Request, payload: OrchestrateRequest):
    """
    Initiates the LangGraph Magic Wand debugging loop and streams progress via SSE.
    """
    # The frontend expects an SSE stream
    return StreamingResponse(
        stream_magic_wand(payload.code, payload.language),
        media_type="text/event-stream"
    )
