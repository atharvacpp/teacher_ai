"""
services/pipeline_b_execution.py — Autonomous Code Execution Pipeline

Graph:
START -> execution -> (error?) -> debugger -> execution ...
"""

import re
from typing import TypedDict
import json
from typing import AsyncGenerator

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END

from config import CHAT_MODEL_ID, DEBUGGER_MODEL, OLLAMA_BASE_URL
from services.mcp_client import run_code as local_run_code


MAX_DEBUG_ATTEMPTS = 3


class AgentStateB(TypedDict):
    """State for Pipeline B."""
    current_code: str
    code_language: str
    execution_output: str
    execution_error: str | None
    has_error: bool
    debug_attempts: int
    images: list[str]


async def execution_node(state: AgentStateB, config: RunnableConfig) -> dict:
    code = state.get("current_code", "").strip()
    if not code:
        return {"execution_output": "", "has_error": False}

    attempt = state.get("debug_attempts", 0) + 1
    print(f"[Execution Node] Running code in Local Sandbox (attempt {attempt}/{MAX_DEBUG_ATTEMPTS})...")

    language = state.get("code_language", "python")

    try:
        output_text, has_error, stderr_text, images = await local_run_code(code, language=language)
        
        execution_error = stderr_text if has_error else None

        if has_error:
            print(f"[Execution Node] \\u274c Code failed:\\n{output_text[:300]}")
        else:
            print(f"[Execution Node] \\u2705 Code executed successfully.")

        return {
            "execution_output": output_text,
            "execution_error": execution_error,
            "has_error": has_error,
            "debug_attempts": attempt,
            "images": images,
        }

    except Exception as exc:
        print(f"[Execution Node] \\u26a0\\ufe0f  Sandbox unavailable: {exc}")
        return {
            "execution_output": f"\\u26a0\\ufe0f Sandbox unavailable: {exc}",
            "execution_error": str(exc),
            "has_error": True,
            "debug_attempts": attempt,
            "images": [],
        }


async def debugger_node(state: AgentStateB, config: RunnableConfig) -> dict:
    attempt = state.get("debug_attempts", 0)
    print(f"[Debugger | LOCAL] Attempting to fix code with {DEBUGGER_MODEL} (after attempt {attempt}/{MAX_DEBUG_ATTEMPTS})...")

    lang = state.get("code_language", "python")

    llm = ChatOllama(
        model=DEBUGGER_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0.1
    )

    system_prompt = (
        f"You are an autonomous debugging tool. You must output ONLY the patched {lang} code "
        f"inside a single markdown block. DO NOT output any explanations, apologies, "
        f"or conversational text. Your output will be parsed by a script."
    )

    user_prompt = f"""Fix the following {lang} code based on the error logs.

--- CODE ---
```{lang}
{state['current_code']}
```

--- ERROR LOGS ---
{state.get('execution_error', state.get('execution_output', 'No output — possible syntax/compilation failure.'))}

Return ONLY the fixed {lang} code in a markdown block."""

    print("[Debugger] Sending error to DeepSeek...")

    try:
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        response_text = response.content
    except Exception as exc:
        print(f"[Debugger | LOCAL] ⚠️ Error querying DeepSeek: {exc}")
        response_text = ""

    print(f"[Debugger] RAW Response from DeepSeek:\n{'-'*40}\n{response_text}\n{'-'*40}")

    pattern = rf"```{lang}\s*\n(.*?)\n?```"
    match = re.search(pattern, response_text, re.DOTALL | re.IGNORECASE)

    if match:
        fixed_code = match.group(1).strip()
    elif response_text:
        generic_match = re.search(r"```[a-zA-Z]*\s*\n(.*?)\n?```", response_text, re.DOTALL)
        if generic_match:
            fixed_code = generic_match.group(1).strip()
        else:
            fixed_code = response_text.strip()
            
            if fixed_code.lower().startswith(f"{lang}\n"):
                fixed_code = fixed_code[len(lang)+1:].strip()
    else:
        fixed_code = state["current_code"]

    print(f"[Debugger] Extracted Code length: {len(fixed_code)} chars")

    return {"current_code": fixed_code}


def route_after_execution(state: AgentStateB) -> str:
    if not state.get("has_error", False):
        return END
    
    if state.get("debug_attempts", 0) >= MAX_DEBUG_ATTEMPTS:
        return END
        
    return "debugger"


workflow_b = StateGraph(AgentStateB)
workflow_b.add_node("execution", execution_node)
workflow_b.add_node("debugger", debugger_node)

workflow_b.add_edge(START, "execution")
workflow_b.add_conditional_edges(
    "execution",
    route_after_execution,
)
workflow_b.add_edge("debugger", "execution")
graph_b = workflow_b.compile()


async def stream_magic_wand(code: str, language: str) -> AsyncGenerator[str, None]:
    """
    Yields JSON-encoded Server-Sent Events (SSE) representing the LangGraph progress for Pipeline B.
    """
    initial_state: AgentStateB = {
        "current_code": code,
        "code_language": language,
        "execution_output": "",
        "has_error": False,
        "debug_attempts": 0,
        "images": [],
    }

    yield "data: " + json.dumps({"type": "log", "message": "Connecting to Local Sandbox..."}) + "\n\n"

    latest_code = code
    latest_output = ""
    latest_has_error = False
    latest_images = []

    try:
        yield "data: " + json.dumps({"type": "log", "message": "Spinning up Docker sandbox..."}) + "\n\n"

        async for output in graph_b.astream(
            initial_state,
            stream_mode="updates",
        ):
            for node_name, state_updates in output.items():
                if node_name == "execution":
                    latest_has_error = state_updates.get("has_error", False)
                    latest_output = state_updates.get("execution_output", latest_output)
                    latest_images = state_updates.get("images", latest_images)
                    if "current_code" in state_updates:
                        latest_code = state_updates["current_code"]

                    if latest_has_error:
                        msg = f"Execution failed. Intercepted traceback and handing over to {DEBUGGER_MODEL}..."
                        yield "data: " + json.dumps({"type": "log", "message": msg}) + "\n\n"
                    else:
                        yield "data: " + json.dumps({"type": "log", "message": "Execution successful. Code is fully verified!"}) + "\n\n"

                elif node_name == "debugger":
                    if "current_code" in state_updates:
                        latest_code = state_updates["current_code"]

                    dbg_err = state_updates.get("debugger_error")
                    if dbg_err:
                        yield "data: " + json.dumps({"type": "log", "message": f"DeepSeek Error: {dbg_err}"}) + "\n\n"
                    else:
                        yield "data: " + json.dumps({"type": "log", "message": "DeepSeek generated a patch. Re-testing in sandbox..."}) + "\n\n"

        yield "data: " + json.dumps({"type": "success", "code": latest_code, "output": latest_output, "images": latest_images}) + "\n\n"

    except Exception as exc:
        print(f"[Magic Wand] Error: {exc}")
        yield "data: " + json.dumps({"type": "error", "message": f"Magic Wand failed: {str(exc)}"}) + "\n\n"
