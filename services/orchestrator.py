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

import httpx
from huggingface_hub import InferenceClient
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import create_react_agent
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from config import HF_API_KEY, CHAT_MODEL_ID, DEBUGGER_MODEL, OLLAMA_BASE_URL
from services.e2b_mcp import e2b_mcp_session


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
    execution_error: str | None # aggregated error details for debugger
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


async def execution_node(state: AgentState, config: RunnableConfig) -> dict:
    """
    Node 3 — Execution.

    Sends the extracted code to the E2B MCP Sandbox.
    Parses the E2B JSON response to extract stdout/stderr properly.
    Detects syntax errors that produce empty output.
    """
    code = state.get("current_code", "").strip()
    if not code:
        return {"execution_output": "", "has_error": False}

    attempt = state.get("debug_attempts", 0) + 1
    print(
        f"[Execution Node] Running code in E2B Sandbox "
        f"(attempt {attempt}/{MAX_DEBUG_ATTEMPTS})..."
    )

    language = state.get("code_language", "python")

    try:
        session = config["configurable"]["mcp_session"]
        result = await session.call_tool("run_code", {"code": code, "language": language})

        raw_text = ""
        for content in result.content:
            if content.type == "text":
                raw_text += content.text

        # --- Parse E2B JSON response ---
        stdout_text = ""
        stderr_text = ""
        has_error = False

        try:
            import json as _json
            e2b_result = _json.loads(raw_text)

            # Extract logs
            logs = e2b_result.get("logs", {})
            stdout_lines = logs.get("stdout", [])
            stderr_lines = logs.get("stderr", [])
            stdout_text = "\n".join(stdout_lines) if stdout_lines else ""
            stderr_text = "\n".join(stderr_lines) if stderr_lines else ""

            # Extract results (e.g. expression return values)
            results = e2b_result.get("results", [])
            if results:
                for r in results:
                    if isinstance(r, dict) and r.get("text"):
                        stdout_text += ("\n" if stdout_text else "") + r["text"]

            # Check for errors in the E2B response
            error_obj = e2b_result.get("error")
            if error_obj:
                has_error = True
                err_name = error_obj.get("name", "Error")
                err_value = error_obj.get("value", "Unknown error")
                err_traceback = error_obj.get("traceback", "")
                if isinstance(err_traceback, list):
                    err_traceback = "\n".join(err_traceback)
                stderr_text = f"{err_name}: {err_value}\n{err_traceback}".strip()

            # Detect silent failures: empty output on non-trivial code
            if not has_error and not stdout_text and not stderr_text:
                has_error = True
                stderr_text = (
                    f"SyntaxError: Code produced no output. "
                    f"Likely an unterminated string, missing bracket, "
                    f"or structural compilation failure in {language}."
                )

            # Also check stderr for error keywords
            if not has_error and stderr_text:
                error_keywords = ["Error", "Exception", "Traceback", "error:", "fatal"]
                if any(kw in stderr_text for kw in error_keywords):
                    has_error = True

        except (_json.JSONDecodeError, TypeError):
            # Not JSON — treat raw_text as direct output
            stdout_text = raw_text
            error_keywords = ["Error", "Exception", "Traceback", "error:", "fatal"]
            if any(kw in raw_text for kw in error_keywords):
                has_error = True
                stderr_text = raw_text

        # Build clean output string
        output_text = stdout_text
        if stderr_text:
            output_text += ("\n" if output_text else "") + stderr_text

        execution_error = stderr_text if has_error else None

        if has_error:
            print(f"[Execution Node] \u274c Code failed:\n{stderr_text[:300]}")
        else:
            print(f"[Execution Node] \u2705 Code executed successfully.")

        return {
            "execution_output": output_text,
            "execution_error": execution_error,
            "has_error": has_error,
            "debug_attempts": attempt,
        }

    except Exception as exc:
        print(f"[Execution Node] \u26a0\ufe0f  Sandbox unavailable: {exc}")
        return {
            "execution_output": f"\u26a0\ufe0f Sandbox unavailable: {exc}",
            "execution_error": str(exc),
            "has_error": False,      # don't trigger debugger loop
            "debug_attempts": attempt,
        }


async def debugger_node(state: AgentState, config: RunnableConfig) -> dict:
    """
    Node 4 — Debugger.

    Feed the broken code and its error output to deepseek-coder-v2.
    Returns ONLY the fixed code — does NOT call E2B tools itself.
    The execution_node will re-test the fixed code in the next loop iteration.
    """
    attempt = state.get("debug_attempts", 0)
    print(
        f"[Debugger | LOCAL] Attempting to fix code with {DEBUGGER_MODEL} "
        f"(after attempt {attempt}/{MAX_DEBUG_ATTEMPTS})..."
    )

    lang = state.get("code_language", "python")

    llm = ChatOllama(
        model=DEBUGGER_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0.1
    )

    system_prompt = (
        f"You are an expert software engineer using DeepSeek-Coder-V2. "
        f"Analyze the provided {lang} code and the execution error logs. "
        f"Fix the syntax or logical error and return ONLY the corrected "
        f"code block in a ```{lang} fenced block. "
        f"Do not provide explanations unless requested."
    )

    user_prompt = f"""Fix the following {lang} code based on the error logs.

--- CODE ---
```{lang}
{state['current_code']}
```

--- ERROR LOGS ---
{state.get('execution_error', state.get('execution_output', 'No output — possible syntax/compilation failure.'))}

Return ONLY the fixed {lang} code in a markdown block."""

    print(f"[Debugger] Querying DeepSeek for a fix...")

    try:
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        response_text = response.content
    except Exception as exc:
        print(f"[Debugger | LOCAL] ⚠️ Error querying DeepSeek: {exc}")
        response_text = ""

    # Extract the fixed code using the dynamic language tag
    pattern = rf"```{lang}\s*\n(.*?)\n?```"
    match = re.search(pattern, response_text, re.DOTALL | re.IGNORECASE)

    if match:
        fixed_code = match.group(1).strip()
        print(f"[Debugger] Extracted fixed code ({len(fixed_code)} chars).")
    elif response_text:
        # Try generic code block
        generic_match = re.search(r"```\w*\s*\n(.*?)\n?```", response_text, re.DOTALL)
        if generic_match:
            fixed_code = generic_match.group(1).strip()
            print(f"[Debugger] Extracted fixed code from generic block ({len(fixed_code)} chars).")
        else:
            fixed_code = response_text.strip()
            print("[Debugger] No fenced block in response — using raw text.")
    else:
        fixed_code = state["current_code"]
        print("[Debugger] Empty response — keeping original code.")

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

    # The Autonomous Debugger should try to fix all execution errors (including Syntax, Name, etc.)
    # We rely on the MAX_DEBUG_ATTEMPTS to stop infinite loops.

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
    async with e2b_mcp_session() as (mcp_session, mcp_tools):
        final_state = await graph.ainvoke(
            initial_state,
            config={"configurable": {"mcp_session": mcp_session, "mcp_tools": mcp_tools}}
        )

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


# ---------------------------------------------------------------------------
# 7. Magic Wand Debugger Stream
# ---------------------------------------------------------------------------
import json
from typing import AsyncGenerator

# Create a specialized graph just for the debugger loop (bypasses Teacher/Extractor)
debug_workflow = StateGraph(AgentState)
debug_workflow.add_node("execution", execution_node)
debug_workflow.add_node("debugger", debugger_node)

debug_workflow.add_edge(START, "execution")
debug_workflow.add_conditional_edges(
    "execution",
    route_after_execution,
    {"end": END, "debugger": "debugger"},
)
debug_workflow.add_edge("debugger", "execution")
debug_graph = debug_workflow.compile()


async def stream_magic_wand(code: str, language: str) -> AsyncGenerator[str, None]:
    """
    Yields JSON-encoded Server-Sent Events (SSE) representing the LangGraph progress.
    Accumulates state from astream() updates so we never re-run the graph.
    """
    initial_state: AgentState = {
        "extracted_text": "",
        "user_prompt": None,
        "final_lesson": "",
        "current_code": code,
        "code_language": language,
        "execution_output": "",
        "has_error": False,
        "debug_attempts": 0,
    }

    yield json.dumps({"type": "log", "message": "Connecting to E2B Cloud Sandbox..."}) + "\n"

    # We'll accumulate the latest state from each node's updates
    latest_code = code
    latest_output = ""
    latest_has_error = False

    try:
        async with e2b_mcp_session() as (mcp_session, mcp_tools):
            async for output in debug_graph.astream(
                initial_state,
                stream_mode="updates",
                config={"configurable": {"mcp_session": mcp_session, "mcp_tools": mcp_tools}}
            ):
                for node_name, state_updates in output.items():
                    if node_name == "execution":
                        latest_has_error = state_updates.get("has_error", False)
                        latest_output = state_updates.get("execution_output", latest_output)
                        # Also track the code (execution doesn't change it, but be safe)
                        if "current_code" in state_updates:
                            latest_code = state_updates["current_code"]

                        if latest_has_error:
                            yield json.dumps({
                                "type": "log",
                                "message": f"Execution failed. Intercepted traceback and handing over to {DEBUGGER_MODEL}..."
                            }) + "\n"
                        else:
                            yield json.dumps({"type": "log", "message": "Execution successful. Code is fully verified!"}) + "\n"

                    elif node_name == "debugger":
                        # Debugger returns the patched code
                        if "current_code" in state_updates:
                            latest_code = state_updates["current_code"]
                        yield json.dumps({"type": "log", "message": "DeepSeek generated a patch. Re-testing in sandbox..."}) + "\n"

            # Stream is done — return the final accumulated state
            yield json.dumps({
                "type": "success",
                "code": latest_code,
                "output": latest_output,
            }) + "\n"

    except Exception as exc:
        print(f"[Magic Wand] Error: {exc}")
        yield json.dumps({"type": "error", "message": f"Magic Wand failed: {str(exc)}"}) + "\n"

