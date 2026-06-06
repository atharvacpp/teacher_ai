"""
routers/pipeline_b_execution.py — Execution and Debugging endpoints.

Contains:
1. /execute-code (Run Code API) -> No debugger, just runs code in sandbox once.
2. /api/orchestrate (Magic Wand API) -> Triggers Pipeline B debug loop.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.mcp_client import run_code
from services.pipeline_b_execution import stream_magic_wand

router = APIRouter(tags=["Pipeline B Execution"])


class ExecuteCodeRequest(BaseModel):
    code: str
    language: str = "python"
    user_input: str = ""


class ExecuteCodeResponse(BaseModel):
    output: str
    has_error: bool
    attempts: int
    max_attempts: int
    language: str
    stderr: str | None = None
    fixed_code: str | None = None


@router.post("/execute-code", response_model=ExecuteCodeResponse)
async def execute_code(payload: ExecuteCodeRequest):
    """
    Execute Python code in the Docker sandbox ONCE (No auto-debug).
    """
    code = payload.code.strip()
    language = payload.language.lower()
    user_input = payload.user_input
    if not code:
        raise HTTPException(status_code=400, detail="No code provided.")

    valid_langs = {"python", "c", "cpp"}
    if language not in valid_langs:
        raise HTTPException(status_code=400, detail=f"Unsupported language: '{language}'")

    print(f"[Pipeline B] /execute-code: Received {len(code)} chars of {language} code")
    
    execution_output = ""
    stderr_output = None
    has_error = False
    attempts = 1

    try:
        execution_output, has_error, stderr_output = await run_code(
            code, language=language, user_input=user_input,
        )
    except Exception as exc:
        execution_output = f"⚠️ Sandbox unavailable: {exc}"
        has_error = False

    return ExecuteCodeResponse(
        output=execution_output,
        has_error=has_error,
        attempts=attempts,
        max_attempts=1, # Auto-execution is completely decoupled from debugger
        language=language,
        stderr=stderr_output,
        fixed_code=None,
    )


class OrchestrateRequest(BaseModel):
    code: str
    language: str
    terminal_error: str | None = None


@router.post("/api/orchestrate")
async def orchestrate_debug(request: Request, payload: OrchestrateRequest):
    """
    Initiates the Pipeline B Magic Wand debugging loop and streams progress via SSE.
    """
    return StreamingResponse(
        stream_magic_wand(payload.code, payload.language),
        media_type="text/event-stream"
    )
