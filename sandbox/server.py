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

import base64
import glob
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
    "python":     None,
    "c":          {"compiler": "gcc", "ext": ".c"},
    "cpp":        {"compiler": "g++", "ext": ".cpp"},
    "javascript": None,
    "bash":       None,
    "java":       None,
}


# ---------------------------------------------------------------------------
# Image Capture
# ---------------------------------------------------------------------------

def _capture_images(tmpdir: str) -> list[str]:
    """Scan tmpdir for images and return them as a list of base64 strings."""
    images = []
    for ext in ("*.png", "*.jpg", "*.jpeg"):
        for filepath in glob.glob(os.path.join(tmpdir, ext)):
            try:
                with open(filepath, "rb") as f:
                    b64_str = base64.b64encode(f.read()).decode("utf-8")
                    images.append(b64_str)
            except Exception as e:
                print(f"Error reading image {filepath}: {e}")
    return images


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
            cwd=tmpdir,
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
        images = _capture_images(tmpdir) if os.path.exists(tmpdir) else []
        if os.path.exists(script_path):
            os.remove(script_path)
        if os.path.exists(tmpdir):
            for file in os.listdir(tmpdir):
                try: os.remove(os.path.join(tmpdir, file))
                except Exception: pass
            os.rmdir(tmpdir)

    return {
        "stdout": stdout_text,
        "stderr": stderr_text,
        "error": error_text,
        "compile_error": None,
        "images": images,
    }

def _run_script(code: str, executor: str, ext: str, user_input: str = "") -> dict:
    """
    Execute an interpreted script (e.g. bash, node).
    """
    tmpdir = tempfile.mkdtemp(prefix="sandbox_")
    script_path = os.path.join(tmpdir, f"script{ext}")

    error_text = None
    stdout_text = ""
    stderr_text = ""

    try:
        with open(script_path, "w") as f:
            f.write(code)

        stdin_arg = subprocess.DEVNULL if not user_input else subprocess.PIPE
        input_data = user_input if user_input else None

        result = subprocess.run(
            [executor, script_path],
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT,
            stdin=stdin_arg,
            input=input_data,
            cwd=tmpdir,
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
        images = _capture_images(tmpdir) if os.path.exists(tmpdir) else []
        if os.path.exists(script_path):
            os.remove(script_path)
        if os.path.exists(tmpdir):
            for file in os.listdir(tmpdir):
                try: os.remove(os.path.join(tmpdir, file))
                except Exception: pass
            os.rmdir(tmpdir)

    return {
        "stdout": stdout_text,
        "stderr": stderr_text,
        "error": error_text,
        "compile_error": None,
        "images": images,
    }


def _run_java(code: str, user_input: str = "") -> dict:
    """
    Compile and run Java code. Assumes class is named Main.
    """
    compile_error = None
    runtime_error = None
    stdout_text = ""
    stderr_text = ""

    tmpdir = tempfile.mkdtemp(prefix="sandbox_")
    src_path = os.path.join(tmpdir, "Main.java")

    try:
        with open(src_path, "w") as f:
            f.write(code)

        # Compile
        compile_result = subprocess.run(
            ["javac", src_path],
            capture_output=True,
            text=True,
            timeout=COMPILE_TIMEOUT,
            cwd=tmpdir,
        )

        if compile_result.returncode != 0:
            compile_error = compile_result.stderr.strip()
            return {
                "stdout": "",
                "stderr": "",
                "error": None,
                "compile_error": compile_error,
            }

        # Run
        stdin_arg = subprocess.DEVNULL if not user_input else subprocess.PIPE
        input_data = user_input if user_input else None

        run_result = subprocess.run(
            ["java", "-cp", tmpdir, "Main"],
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT,
            stdin=stdin_arg,
            input=input_data,
            cwd=tmpdir,
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
        images = _capture_images(tmpdir) if os.path.exists(tmpdir) else []
        if os.path.exists(src_path):
            os.remove(src_path)
        class_file = os.path.join(tmpdir, "Main.class")
        if os.path.exists(class_file):
            os.remove(class_file)
        if os.path.exists(tmpdir):
            for file in os.listdir(tmpdir):
                try: os.remove(os.path.join(tmpdir, file))
                except Exception: pass
            os.rmdir(tmpdir)

    return {
        "stdout": stdout_text,
        "stderr": stderr_text,
        "error": runtime_error,
        "compile_error": compile_error,
        "images": images,
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
            cwd=tmpdir,
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
            cwd=tmpdir,
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
        images = _capture_images(tmpdir) if os.path.exists(tmpdir) else []
        for path in (src_path, bin_path):
            if os.path.exists(path):
                os.remove(path)
        if os.path.exists(tmpdir):
            for file in os.listdir(tmpdir):
                try: os.remove(os.path.join(tmpdir, file))
                except Exception: pass
            os.rmdir(tmpdir)

    return {
        "stdout": stdout_text,
        "stderr": stderr_text,
        "error": runtime_error,
        "compile_error": compile_error,
        "images": images,
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
            "error": f"Unsupported language: '{language}'. Use python, c, cpp, javascript, java, or bash.",
            "compile_error": None,
            "images": [],
        })
        return payload

    if language == "python":
        result = _run_python(code, user_input=user_input)
    elif language == "javascript":
        result = _run_script(code, "node", ".js", user_input=user_input)
    elif language == "bash":
        result = _run_script(code, "bash", ".sh", user_input=user_input)
    elif language == "java":
        result = _run_java(code, user_input=user_input)
    else:
        result = _run_compiled(code, language, user_input=user_input)

    return json.dumps(result)


@mcp.tool()
def execute_bash_command(command: str) -> str:
    """
    Execute an arbitrary Bash command inside the sandbox container.
    This gives autonomous agents the ability to run pip install, npm install,
    or investigate the file system.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT
        )
        return json.dumps({
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        })
    except subprocess.TimeoutExpired:
        return json.dumps({
            "stdout": "",
            "stderr": f"Timeout Error: Command exceeded {RUN_TIMEOUT}s limit.",
            "returncode": 1
        })
    except Exception as e:
        return json.dumps({
            "stdout": "",
            "stderr": str(e),
            "returncode": 1
        })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
