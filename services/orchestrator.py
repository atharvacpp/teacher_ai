"""
services/orchestrator.py — Phase 5 LangGraph State Machine (Code Execution)

Multi-agent workflow with a self-correcting debugger loop:

  Node 1 — Teacher  (Qwen 2.5 via HuggingFace)
    Generates a markdown lesson with Python code examples from the
    extracted document content.

  Node 2 — Code Extractor  (pure Python / regex)
    Scans the lesson for the first ```python fenced code block.

  Node 3 — Execution  (MCP → Docker sandbox)
    Sends the extracted code to the Docker sandbox, captures output.

  Node 4 — Debugger  (Qwen 2.5 via HuggingFace, max 3 attempts)
    Reads error logs, fixes the code, and loops back to Execution.

  Graph:
    START → teacher → code_extractor ─┬─ (no code)  → END
                                       └─ (has code) → execution ─┬─ (ok)           → END
                                                                    ├─ (err, <3 att.) → debugger → execution
                                                                    └─ (err, ≥3 att.) → END
"""

import re
from typing import TypedDict

from huggingface_hub import InferenceClient
from langgraph.graph import StateGraph, START, END

from config import HF_API_KEY, CHAT_MODEL_ID
from services.mcp_client import run_code


# ---------------------------------------------------------------------------
# Constants & Clients
# ---------------------------------------------------------------------------

REASONING_MODEL = CHAT_MODEL_ID       # "Qwen/Qwen2.5-7B-Instruct"
MAX_DEBUG_ATTEMPTS = 3                # total execution attempts before giving up

_hf_client = InferenceClient(api_key=HF_API_KEY)


# ---------------------------------------------------------------------------
# 1. State Definition
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    """Shared state passed between every node in the graph."""
    extracted_text: str         # document content (from the upload pipeline)
    user_prompt: str | None     # optional student question / context
    final_lesson: str           # teacher-generated markdown lesson
    current_code: str           # code extracted from the lesson
    code_language: str          # "python" | "c" | "cpp"
    execution_output: str       # stdout / traceback from the sandbox
    has_error: bool             # True when code execution raised an exception
    debug_attempts: int         # number of execution attempts so far


# ---------------------------------------------------------------------------
# 2. Model Helper
# ---------------------------------------------------------------------------

def _hf_reasoning_call(prompt: str, *, max_tokens: int = 2048) -> str:
    """
    Send a text-only prompt to Qwen 2.5-7B-Instruct via HuggingFace.

    Safety: the payload is a plain {role, content} message — no images,
    no binary attachments.
    """
    messages = [{"role": "user", "content": prompt}]

    print(f"[Reasoning | CLOUD] Calling {REASONING_MODEL} via HuggingFace ...")
    response = _hf_client.chat_completion(
        model=REASONING_MODEL,
        messages=messages,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


# ---------------------------------------------------------------------------
# 3. Nodes
# ---------------------------------------------------------------------------

def teacher_node(state: AgentState) -> dict:
    """
    Node 1 — Teacher.

    Generate a polished markdown lesson from the extracted content.
    Instructs the model to include working Python code examples inside
    ```python fenced blocks so downstream nodes can verify them.
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


def code_extractor_node(state: AgentState) -> dict:
    """
    Node 2 — Code Extractor.

    Scan the lesson for the first ```python ... ``` fenced code block.
    If found, save it to `current_code`.  If not, set `current_code`
    to empty string so the router skips execution.
    """
    print("[Code Extractor] Scanning lesson for Python code blocks...")

    pattern = r"```python\s*\n(.*?)```"
    match = re.search(pattern, state["final_lesson"], re.DOTALL)

    if match:
        code = match.group(1).strip()
        print(f"[Code Extractor] Found {len(code)} chars of Python code.")
        return {"current_code": code}

    print("[Code Extractor] No Python code blocks found — skipping execution.")
    return {"current_code": ""}


async def execution_node(state: AgentState) -> dict:
    """
    Node 3 — Execution (async).

    Send `current_code` to the Docker sandbox via the MCP client.
    Capture stdout / error output and increment the attempt counter.

    If the sandbox is unreachable (Docker not running, image not built),
    the error is recorded but `has_error` is set to False so the
    debugger loop does NOT fire (can't fix infrastructure issues).
    """
    code = state.get("current_code", "").strip()
    if not code:
        return {"execution_output": "", "has_error": False}

    attempt = state.get("debug_attempts", 0) + 1
    print(
        f"[Execution Node] Running code in Docker sandbox "
        f"(attempt {attempt}/{MAX_DEBUG_ATTEMPTS})..."
    )

    language = state.get("code_language", "python")

    try:
        output, has_error = await run_code(code, language=language)

        if has_error:
            print(f"[Execution Node] ❌ Code failed:\n{output[:300]}")
        else:
            print(f"[Execution Node] ✅ Code executed successfully.")

        return {
            "execution_output": output,
            "has_error": has_error,
            "debug_attempts": attempt,
        }

    except Exception as exc:
        # Infrastructure failure (Docker down, image missing, MCP SDK absent)
        print(f"[Execution Node] ⚠️  Sandbox unavailable: {exc}")
        return {
            "execution_output": f"⚠️ Sandbox unavailable: {exc}",
            "has_error": False,      # don't trigger debugger loop
            "debug_attempts": attempt,
        }


def debugger_node(state: AgentState) -> dict:
    """
    Node 4 — Debugger.

    Feed the broken code and its error output to Qwen 2.5 and ask it
    to return a fixed version.  The corrected code is saved back to
    `current_code` so the graph loops back to execution_node.
    """
    attempt = state.get("debug_attempts", 0)
    print(
        f"[Debugger | CLOUD] Attempting to fix code "
        f"(after attempt {attempt}/{MAX_DEBUG_ATTEMPTS})..."
    )

    prompt = (
        "You are an expert Python debugger. The following code produced "
        "an error when executed. Analyze the error, fix the bug, and "
        "return ONLY the corrected Python code inside a single "
        "```python fenced block. Do NOT include any explanation — "
        "just the fixed code.\n\n"
        f"--- Broken Code ---\n"
        f"```python\n{state['current_code']}\n```\n\n"
        f"--- Error Output ---\n"
        f"```\n{state['execution_output']}\n```"
    )

    response = _hf_reasoning_call(prompt, max_tokens=1024)

    # Extract the fixed code from the fenced block
    pattern = r"```python\s*\n(.*?)```"
    match = re.search(pattern, response, re.DOTALL)

    if match:
        fixed_code = match.group(1).strip()
        print(f"[Debugger] Extracted fixed code ({len(fixed_code)} chars).")
    else:
        # Fallback: treat the entire response as code
        fixed_code = response.strip()
        print("[Debugger] No fenced block in response — using raw text.")

    return {"current_code": fixed_code}


# ---------------------------------------------------------------------------
# 4. Routing Functions (conditional edges)
# ---------------------------------------------------------------------------

def route_after_extraction(state: AgentState) -> str:
    """After code_extractor: execute if code was found, else skip to END."""
    if state.get("current_code", "").strip():
        return "execute"
    return "end"


def route_after_execution(state: AgentState) -> str:
    """
    After execution: decide whether to retry via debugger or stop.

    Short-circuits to END immediately for errors that are NOT worth
    burning a debugger round-trip on:
      • SyntaxError / IndentationError  — the student needs to see these
      • Compilation errors (C/C++)       — same, surface directly
      • Timeout errors                   — the code is too slow, not buggy
      • NameError / ImportError          — usually a missing dependency
    """
    if not state.get("has_error", False):
        return "end"

    output = state.get("execution_output", "")
    lower_output = output.lower()

    # ── Non-retryable errors: surface immediately, don't waste LLM calls ──
    non_retryable_patterns = [
        "syntaxerror",
        "indentationerror",
        "nameerror",
        "importerror",
        "modulenotfounderror",
        "[compilation error]",
        "timeout error",
    ]

    for pattern in non_retryable_patterns:
        if pattern in lower_output:
            print(
                f"[Router] Non-retryable error detected ('{pattern}') "
                f"— skipping debugger, surfacing to user."
            )
            return "end"

    # ── Max attempts reached ──
    if state.get("debug_attempts", 0) >= MAX_DEBUG_ATTEMPTS:
        print(
            f"[Router] Max debug attempts ({MAX_DEBUG_ATTEMPTS}) reached "
            f"— returning lesson with error output."
        )
        return "end"

    return "debugger"



# ---------------------------------------------------------------------------
# 5. Graph Compilation
# ---------------------------------------------------------------------------

workflow = StateGraph(AgentState)

# ── Register nodes ──
workflow.add_node("teacher",        teacher_node)          # Qwen 2.5 (HF)
workflow.add_node("code_extractor", code_extractor_node)   # regex
workflow.add_node("execution",      execution_node)        # MCP → Docker
workflow.add_node("debugger",       debugger_node)         # Qwen 2.5 (HF)

# ── Linear edges ──
workflow.add_edge(START, "teacher")
workflow.add_edge("teacher", "code_extractor")

# ── Conditional: skip execution if no code ──
workflow.add_conditional_edges(
    "code_extractor",
    route_after_extraction,
    {"execute": "execution", "end": END},
)

# ── Conditional: debugger loop or END ──
workflow.add_conditional_edges(
    "execution",
    route_after_execution,
    {"end": END, "debugger": "debugger"},
)

# ── Debugger always loops back to execution ──
workflow.add_edge("debugger", "execution")

# ── Compile ──
graph = workflow.compile()


# ---------------------------------------------------------------------------
# 6. Public Entry Point
# ---------------------------------------------------------------------------

async def run_upload_workflow(
    extracted_text: str,
    user_prompt: str | None = None,
) -> str:
    """
    Run the full LangGraph pipeline:
      Teacher → Code Extractor → Execution → (Debugger loop) → END

    Called from the /upload FastAPI endpoint after text extraction.

    Args:
        extracted_text: The document content (from PyMuPDF or LLaVA).
        user_prompt:    Optional student question / context.

    Returns:
        The final lesson markdown, with a code-output section appended
        if any code was executed.
    """
    initial_state: AgentState = {
        "extracted_text": extracted_text,
        "user_prompt": user_prompt,
        "final_lesson": "",
        "current_code": "",
        "code_language": "python",
        "execution_output": "",
        "has_error": False,
        "debug_attempts": 0,
    }

    # ainvoke runs async nodes natively and wraps sync nodes in threads
    final_state = await graph.ainvoke(initial_state)

    # ── Assemble the final output ──
    lesson = final_state["final_lesson"]
    code = final_state.get("current_code", "").strip()
    output = final_state.get("execution_output", "").strip()
    has_error = final_state.get("has_error", False)
    attempts = final_state.get("debug_attempts", 0)

    if code and output:
        if has_error:
            lesson += (
                f"\n\n---\n"
                f"### ⚠️ Code Output "
                f"(errors after {attempts} attempt{'s' if attempts != 1 else ''})\n"
                f"```\n{output}\n```"
            )
        else:
            lesson += (
                f"\n\n---\n"
                f"### ✅ Code Output (verified)\n"
                f"```\n{output}\n```"
            )

    print("[Orchestrator] Workflow complete.")
    return lesson
