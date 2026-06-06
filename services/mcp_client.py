"""
services/mcp_client.py — Async MCP client bridge for the Docker code sandbox.

Connects to the explainai-sandbox Docker container via stdio,
calls the `execute_code` tool, and returns the captured output.

Each call spins up a fresh container (--rm auto-cleans), providing
complete isolation between executions.

Supported languages: python, c, cpp.

Usage:
    from services.mcp_client import run_code

    output, has_error, stderr = await run_code("print(1 + 1)", language="python")
    output, has_error, stderr = await run_code(
        'name = input()\\nprint(f"Hello {name}")',
        language="python",
        user_input="World",
    )
"""

import json
import os
import shutil

# ---------------------------------------------------------------------------
# Graceful import — app still starts if `mcp` SDK is not installed
# ---------------------------------------------------------------------------
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    import mcp.types as types

    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False

# ---------------------------------------------------------------------------
# Docker sandbox configuration
# ---------------------------------------------------------------------------

_SANDBOX_PARAMS = None
if _MCP_AVAILABLE:
    cmd = "docker"
    if os.name == "nt":
        resolved_cmd = shutil.which(cmd)
        if resolved_cmd:
            cmd = resolved_cmd
        else:
            raise RuntimeError(
                "Docker is not installed or not in PATH. Please install Docker Desktop for Windows."
            )

    _SANDBOX_PARAMS = StdioServerParameters(
        command=cmd,
        args=[
            "run", "-i", "--rm",
            "--network", "none",       # no internet access
            "--memory", "256m",        # cap memory at 256 MB
            "--cpus", "0.5",           # cap CPU at 50 %
            "--pids-limit", "64",      # cap process count
            "-e", "PYTHONUNBUFFERED=1",# Prevent stdout buffering
            "explainai-sandbox",       # image name (built from sandbox/Dockerfile)
        ],
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

VALID_LANGUAGES = {"python", "c", "cpp"}


async def run_code(
    code: str,
    language: str = "python",
    user_input: str = "",
) -> tuple[str, bool, str | None]:
    """
    Execute code inside the Docker sandbox via MCP.

    Spins up a fresh Docker container, sends the code to the
    ``execute_code`` MCP tool, and tears down the container.

    Args:
        code:       Source code to execute.
        language:   One of "python", "c", or "cpp".
        user_input: Optional stdin data fed to the subprocess (for input()/scanf/cin).

    Returns:
        A tuple of (output_text, has_error, stderr_text).
        ``output_text`` contains stdout and, if an error occurred,
        the full traceback / compile error appended after a blank line.
        ``has_error`` is True when the code failed to compile or run.
        ``stderr_text`` is the raw stderr output (None if no stderr).

    Raises:
        RuntimeError: If the ``mcp`` SDK is not installed.
        ValueError: If the language is not supported.
        Exception: If Docker is not running or the image is not built.
    """
    if not _MCP_AVAILABLE:
        raise RuntimeError(
            "MCP SDK is not installed.  Run:  pip install mcp"
        )

    language = language.lower()
    if language not in VALID_LANGUAGES:
        raise ValueError(
            f"Unsupported language: '{language}'. Must be one of: {VALID_LANGUAGES}"
        )

    # Build the arguments dict — include user_input only if provided
    tool_args = {"code": code, "language": language}
    if user_input:
        tool_args["user_input"] = user_input

    async with stdio_client(_SANDBOX_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool(
                "execute_code",
                arguments=tool_args,
            )

            # ── Parse the JSON payload from the sandbox server ──
            raw_text = ""
            for content in result.content:
                if isinstance(content, types.TextContent):
                    raw_text += content.text

            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError:
                # Fallback: treat the raw text as output
                return (raw_text or "(no output)"), True, None

            stdout = data.get("stdout", "")
            stderr = data.get("stderr", "")
            error = data.get("error")
            compile_error = data.get("compile_error")

            # Determine if there was any error
            has_error = (error is not None) or (compile_error is not None)

            # Combine stdout + compile_error + runtime error for the
            # backwards-compatible output string
            output = ""
            if compile_error:
                output += f"[Compilation Error]\n{compile_error}\n"
            if stdout:
                output += stdout
            if error:
                if output and not output.endswith("\n"):
                    output += "\n"
                output += error

            # Return stderr separately so the frontend can render it
            stderr_out = stderr.strip() if stderr else None

            return (output.strip() if output else "(no output)"), has_error, stderr_out
