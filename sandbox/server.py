"""
sandbox/server.py — FastMCP code-execution server (runs inside Docker).

Exposes an `execute_code` tool that accepts a code string, a language
parameter ("python", "c", or "cpp"), and an optional user_input string
for stdin.  Communicates with the host via stdio (JSON-RPC).

Execution strategy (all via subprocess with 10-second hard timeouts):
  • Python  — write to script.py → subprocess python3 script.py
  • C       — write to code.c   → gcc code.c -o code_exec → ./code_exec
  • C++     — write to code.cpp  → g++ code.cpp -o code_exec → ./code_exec

Returns JSON with 'stdout', 'stderr', 'error', and 'compile_error' fields.

This file is COPIED into the Docker image at build time — it does NOT
run on the host machine.
"""

import json
import os
import subprocess
import tempfile
import traceback

from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# FastMCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP("ExplainAISandbox")

# Timeouts (seconds)
COMPILE_TIMEOUT = 10
RUN_TIMEOUT = 10

# Supported languages and their compilers
LANGUAGE_CONFIG = {
    "python": None,                       # subprocess python3, no compiler
    "c":      {"compiler": "gcc", "ext": ".c"},
    "cpp":    {"compiler": "g++", "ext": ".cpp"},
}


# ---------------------------------------------------------------------------
# Language Handlers
# ---------------------------------------------------------------------------

def _run_python(code: str, user_input: str = "") -> dict:
    """
    Execute Python code via subprocess with a strict timeout.

    Writes code to a temp file and runs `python3 script.py` as a
    subprocess.  If user_input is provided, it is fed to stdin so
    input() calls resolve instantly.
    """
    tmpdir = tempfile.mkdtemp(prefix="sandbox_")
    script_path = os.path.join(tmpdir, "script.py")

    error_text = None
    stdout_text = ""
    stderr_text = ""

    try:
        with open(script_path, "w") as f:
            f.write(code)

        # If user_input is provided, feed it to stdin; otherwise /dev/null
        stdin_arg = subprocess.DEVNULL if not user_input else subprocess.PIPE
        input_data = user_input if user_input else None

        result = subprocess.run(
            ["python3", script_path],
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT,
            stdin=stdin_arg,
            input=input_data,
        )

        stdout_text = result.stdout
        stderr_text = result.stderr
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
        "stderr": stderr_text,
        "error": error_text,
        "compile_error": None,
    }


def _run_compiled(code: str, language: str, user_input: str = "") -> dict:
    """
    Compile and run C or C++ code.

    Steps:
      1. Write code to code.c or code.cpp.
      2. Compile: gcc code.c -o code_exec  (or g++ code.cpp -o code_exec).
      3. Run: ./code_exec — stdin fed from user_input if provided.
      4. Clean up temp files.

    Strict timeouts on both compilation and execution.
    """
    config = LANGUAGE_CONFIG[language]
    compiler = config["compiler"]
    ext = config["ext"]

    compile_error = None
    runtime_error = None
    stdout_text = ""
    stderr_text = ""

    tmpdir = tempfile.mkdtemp(prefix="sandbox_")
    src_path = os.path.join(tmpdir, f"code{ext}")
    bin_path = os.path.join(tmpdir, "code_exec")

    try:
        # 1. Write source file
        with open(src_path, "w") as f:
            f.write(code)

        # 2. Compile — strict timeout
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
                "stderr": "",
                "error": None,
                "compile_error": compile_error,
            }

        # 3. Run the compiled binary — stdin fed from user_input if provided
        stdin_arg = subprocess.DEVNULL if not user_input else subprocess.PIPE
        input_data = user_input if user_input else None

        run_result = subprocess.run(
            [bin_path],
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT,
            stdin=stdin_arg,
            input=input_data,
        )

        stdout_text = run_result.stdout
        stderr_text = run_result.stderr
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
        "stderr": stderr_text,
        "error": runtime_error,
        "compile_error": compile_error,
    }


# ---------------------------------------------------------------------------
# MCP Tool (auto-generates JSON schema from type hints)
# ---------------------------------------------------------------------------

@mcp.tool()
def execute_code(
    code: str,
    language: str = "python",
    user_input: str = "",
) -> str:
    """
    Execute a code snippet in an isolated sandbox.

    Supports Python, C, and C++.
    Returns JSON with 'stdout', 'stderr', 'error', and 'compile_error' fields.

    Args:
        code: The source code to execute.
        language: The programming language — "python", "c", or "cpp".
        user_input: Optional stdin data fed to the process (for input()/scanf/cin).
    """
    language = language.lower()

    if language not in LANGUAGE_CONFIG:
        payload = json.dumps({
            "stdout": "",
            "stderr": "",
            "error": f"Unsupported language: '{language}'. Use python, c, or cpp.",
            "compile_error": None,
        })
        return payload

    if language == "python":
        result = _run_python(code, user_input=user_input)
    else:
        result = _run_compiled(code, language, user_input=user_input)

    return json.dumps(result)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
