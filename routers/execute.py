"""
routers/execute.py — POST /execute-code endpoint (Phase 5: Code Sandbox).

Accepts raw Python code from the frontend code editor, runs it through
the LangGraph self-correcting pipeline (execute → debug → retry), and
returns the full execution output with debugging metadata.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.orchestrator import (
    graph,
    AgentState,
    MAX_DEBUG_ATTEMPTS,
)

router = APIRouter(tags=["Code Execution"])


# ---------------------------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------------------------

class ExecuteCodeRequest(BaseModel):
    code: str
    language: str = "python"  # "python" | "c" | "cpp"


class ExecuteCodeResponse(BaseModel):
    output: str
    has_error: bool
    attempts: int
    max_attempts: int
    language: str
    fixed_code: str | None = None


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/execute-code", response_model=ExecuteCodeResponse)
async def execute_code(payload: ExecuteCodeRequest):
    """
    Execute Python code in the Docker sandbox with self-correcting debug loop.

    The LangGraph pipeline:
      execution_node → (error?) → debugger_node → execution_node → … (max 3)

    Returns the final output, whether errors persist, how many attempts
    were needed, and the corrected code if the debugger modified it.
    """
    code = payload.code.strip()
    language = payload.language.lower()
    if not code:
        raise HTTPException(status_code=400, detail="No code provided.")

    valid_langs = {"python", "c", "cpp"}
    if language not in valid_langs:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language: '{language}'. Must be one of: {valid_langs}",
        )

    print("=" * 60)
    print(f"[Execute] Received {len(code)} chars of {language} code")
    print("=" * 60)

    # Build a minimal state — we skip teacher + code_extractor and jump
    # straight to the execution node by pre-filling current_code.
    # To do this we use a small dedicated graph that only has
    # execution + debugger nodes.  But since our main graph requires
    # extracted_text and the teacher node to fire first, we'll call
    # run_code directly here for a cleaner API.

    from services.mcp_client import run_code

    original_code = code
    current_code = code
    execution_output = ""
    has_error = False
    attempts = 0

    for attempt in range(1, MAX_DEBUG_ATTEMPTS + 1):
        attempts = attempt
        print(f"[Execute] Attempt {attempt}/{MAX_DEBUG_ATTEMPTS}...")

        try:
            execution_output, has_error = await run_code(current_code, language=language)
        except Exception as exc:
            execution_output = f"⚠️ Sandbox unavailable: {exc}"
            has_error = False  # Don't trigger debugger for infra errors
            break

        if not has_error:
            print(f"[Execute] ✅ Code ran successfully on attempt {attempt}.")
            break

        # If there are more attempts, run the debugger
        if attempt < MAX_DEBUG_ATTEMPTS:
            print(f"[Execute] ❌ Error — invoking debugger...")
            from services.orchestrator import _hf_reasoning_call
            import re

            # Map language to fenced code block name
            fence_lang = {"python": "python", "c": "c", "cpp": "cpp"}[language]
            lang_label = {"python": "Python", "c": "C", "cpp": "C++"}[language]

            prompt = (
                f"You are an expert {lang_label} debugger. The following code "
                "produced an error. Fix the bug and return ONLY the "
                f"corrected code inside a single ```{fence_lang} fenced block. "
                "No explanation.\n\n"
                f"--- Broken Code ---\n```{fence_lang}\n{current_code}\n```\n\n"
                f"--- Error Output ---\n```\n{execution_output}\n```"
            )

            response = _hf_reasoning_call(prompt, max_tokens=1024)

            pattern = rf"```{fence_lang}\s*\n(.*?)```"
            match = re.search(pattern, response, re.DOTALL)
            current_code = match.group(1).strip() if match else response.strip()
            print(f"[Execute] Debugger produced {len(current_code)} chars of fixed code.")

    # Did the debugger change the code?
    fixed_code = current_code if current_code != original_code else None

    return ExecuteCodeResponse(
        output=execution_output,
        has_error=has_error,
        attempts=attempts,
        max_attempts=MAX_DEBUG_ATTEMPTS,
        language=language,
        fixed_code=fixed_code,
    )
