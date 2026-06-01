"""
sandbox/server.py — MCP code-execution server (runs inside Docker).

Exposes an `execute_code` tool that accepts a code string and a language
parameter ("python", "c", or "cpp").  Communicates with the host via
stdio (JSON-RPC).

Execution strategy (all via subprocess with 3-second hard timeouts):
  • Python  — write to script.py → subprocess python3 script.py
  • C       — write to code.c   → gcc code.c -o code_exec → ./code_exec
  • C++     — write to code.cpp  → g++ code.cpp -o code_exec → ./code_exec

Returns JSON with 'stdout', 'error', and 'compile_error' fields.

This file is COPIED into the Docker image at build time — it does NOT
run on the host machine.
"""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import traceback

from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

app = Server("explainai-sandbox")

# Timeouts (seconds)
COMPILE_TIMEOUT = 3
RUN_TIMEOUT = 3

# Supported languages and their compilers
LANGUAGE_CONFIG = {
    "python": None,                       # subprocess python3, no compiler
    "c":      {"compiler": "gcc", "ext": ".c"},
    "cpp":    {"compiler": "g++", "ext": ".cpp"},
}


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    """Advertise the execute_code tool to MCP clients."""
    return [
        types.Tool(
            name="execute_code",
            description=(
                "Execute a code snippet in an isolated sandbox. "
                "Supports Python, C, and C++. "
                "Returns JSON with 'stdout', 'error', and 'compile_error' fields."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The source code to execute.",
                    },
                    "language": {
                        "type": "string",
                        "enum": ["python", "c", "cpp"],
                        "description": "The programming language of the code.",
                        "default": "python",
                    },
                },
                "required": ["code"],
            },
        )
    ]


# ---------------------------------------------------------------------------
# Language Handlers
# ---------------------------------------------------------------------------

def _run_python(code: str) -> dict:
    """
    Execute Python code via subprocess with a strict timeout.

    Writes code to a temp file and runs `python3 script.py` as a
    subprocess.  stdin is piped from /dev/null so the process never
    hangs waiting for input().
    """
    tmpdir = tempfile.mkdtemp(prefix="sandbox_")
    script_path = os.path.join(tmpdir, "script.py")

    error_text = None
    stdout_text = ""

    try:
        with open(script_path, "w") as f:
            f.write(code)

        result = subprocess.run(
            ["python3", script_path],
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT,
            stdin=subprocess.DEVNULL,   # never hang on input()
        )

        stdout_text = result.stdout
        if result.returncode != 0:
            error_text = result.stderr.strip()
            if not error_text:
                error_text = f"Process exited with code {result.returncode}"

    except subprocess.TimeoutExpired:
        error_text = f"Timeout Error: execution exceeded {RUN_TIMEOUT}s limit."
    except Exception:
        error_text = traceback.format_exc()
    finally:
        if os.path.exists(script_path):
            os.remove(script_path)
        if os.path.exists(tmpdir):
            os.rmdir(tmpdir)

    return {
        "stdout": stdout_text,
        "error": error_text,
        "compile_error": None,
    }


def _run_compiled(code: str, language: str) -> dict:
    """
    Compile and run C or C++ code.

    Steps:
      1. Write code to code.c or code.cpp.
      2. Compile: gcc code.c -o code_exec  (or g++ code.cpp -o code_exec).
      3. Run: ./code_exec — stdin piped from /dev/null.
      4. Clean up temp files.

    Strict 3-second timeout on both compilation and execution.
    """
    config = LANGUAGE_CONFIG[language]
    compiler = config["compiler"]
    ext = config["ext"]

    compile_error = None
    runtime_error = None
    stdout_text = ""

    tmpdir = tempfile.mkdtemp(prefix="sandbox_")
    src_path = os.path.join(tmpdir, f"code{ext}")
    bin_path = os.path.join(tmpdir, "code_exec")

    try:
        # 1. Write source file
        with open(src_path, "w") as f:
            f.write(code)

        # 2. Compile — strict 3s timeout
        compile_result = subprocess.run(
            [compiler, src_path, "-o", bin_path, "-lm"],
            capture_output=True,
            text=True,
            timeout=COMPILE_TIMEOUT,
        )

        if compile_result.returncode != 0:
            compile_error = compile_result.stderr.strip()
            return {
                "stdout": "",
                "error": None,
                "compile_error": compile_error,
            }

        # 3. Run the compiled binary — strict 3s timeout
        run_result = subprocess.run(
            [bin_path],
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT,
            stdin=subprocess.DEVNULL,   # never hang on scanf()
        )

        stdout_text = run_result.stdout
        if run_result.returncode != 0:
            runtime_error = run_result.stderr.strip()
            if not runtime_error:
                runtime_error = f"Process exited with code {run_result.returncode}"

    except subprocess.TimeoutExpired:
        runtime_error = f"Timeout Error: execution exceeded {RUN_TIMEOUT}s limit."
    except Exception:
        runtime_error = traceback.format_exc()
    finally:
        for path in (src_path, bin_path):
            if os.path.exists(path):
                os.remove(path)
        if os.path.exists(tmpdir):
            os.rmdir(tmpdir)

    return {
        "stdout": stdout_text,
        "error": runtime_error,
        "compile_error": compile_error,
    }


# ---------------------------------------------------------------------------
# Tool Dispatcher
# ---------------------------------------------------------------------------

@app.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[types.TextContent]:
    """
    Handle an execute_code tool call.

    Routes to the correct handler based on the `language` argument.
    """
    if name != "execute_code":
        raise ValueError(f"Unknown tool: {name}")

    code = arguments.get("code", "")
    language = arguments.get("language", "python").lower()

    if language not in LANGUAGE_CONFIG:
        payload = json.dumps({
            "stdout": "",
            "error": f"Unsupported language: '{language}'. Use python, c, or cpp.",
            "compile_error": None,
        })
        return [types.TextContent(type="text", text=payload)]

    if language == "python":
        result = _run_python(code)
    else:
        result = _run_compiled(code, language)

    payload = json.dumps(result)
    return [types.TextContent(type="text", text=payload)]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
