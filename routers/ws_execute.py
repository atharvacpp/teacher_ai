"""
routers/ws_execute.py — WebSocket code-execution endpoint (Phase 5.1).

Provides a real-time, interactive terminal experience via Docker:
  1. Frontend opens WS to /ws/execute
  2. Sends JSON init: { "code": "...", "language": "python" }
  3. Backend writes code to a temp dir, volume-mounts it into Docker
  4. Docker container runs the code, stdout/stderr stream to WS in real-time
  5. Frontend keystrokes arrive as WS text messages → piped to container stdin
  6. On process exit → send exit status → close WS

Uses asyncio.create_subprocess_exec to spawn Docker with interactive stdin.
Python runs with -u (unbuffered) so prompts flush immediately.
C/C++ binaries run via stdbuf -oL for line-buffered output.
"""

import asyncio
import json
import os
import shutil
import tempfile

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["WebSocket Execution"])

# Timeouts
RUN_TIMEOUT = 30  # seconds

# Docker image name (must match sandbox/Dockerfile build)
DOCKER_IMAGE = "explainai-sandbox"

# Supported languages
LANGUAGE_CONFIG = {
    "python": None,
    "c":      {"compiler": "gcc", "ext": ".c"},
    "cpp":    {"compiler": "g++", "ext": ".cpp"},
}

# ANSI escape codes for coloring
ANSI_RED = "\033[31m"
ANSI_YELLOW = "\033[33m"
ANSI_RESET = "\033[0m"
ANSI_DIM = "\033[2m"

import anyio

# ---------------------------------------------------------------------------
# Resolve Docker executable (Windows needs full path)
# ---------------------------------------------------------------------------

_DOCKER_CMD = "docker"
if os.name == "nt":
    _resolved = shutil.which("docker")
    if _resolved:
        _DOCKER_CMD = _resolved
    else:
        print("[ws_execute] WARNING: Docker not found in PATH.")


def _docker_base_args():
    """Return the common docker run arguments."""
    return [
        _DOCKER_CMD, "run", "-i", "--rm",
        "--network", "none",        # no internet access
        "--memory", "256m",         # cap memory at 256 MB
        "--cpus", "0.5",            # cap CPU at 50 %
        "--pids-limit", "64",       # cap process count
    ]


import threading
import subprocess
import time

def _stream_output(
    pipe,
    websocket: WebSocket,
    loop: asyncio.AbstractEventLoop,
    is_stderr: bool = False,
):
    """
    Read from a subprocess pipe in a background thread and forward chunks
    to WebSocket via the main event loop in a thread-safe manner.
    """
    try:
        import os
        # Read byte chunks to stream output as fast as possible
        while True:
            chunk = os.read(pipe.fileno(), 1024)
            if not chunk:
                break
            text = chunk.decode("utf-8", errors="replace")
            # Replace bare \n with \r\n for xterm compatibility
            text = text.replace("\r\n", "\n").replace("\n", "\r\n")
            if is_stderr:
                asyncio.run_coroutine_threadsafe(websocket.send_text(f"{ANSI_RED}{text}{ANSI_RESET}"), loop)
            else:
                asyncio.run_coroutine_threadsafe(websocket.send_text(text), loop)
    except Exception:
        pass


async def _forward_stdin(
    websocket: WebSocket,
    proc: subprocess.Popen,
):
    """
    Listen for incoming WebSocket text messages and write them
    to the synchronous subprocess stdin.
    """
    try:
        while proc.poll() is None:
            data = await websocket.receive_text()
            if proc.poll() is not None:
                break
            if proc.stdin:
                # Xterm.js sends \r for Enter, but Linux expects \n
                data = data.replace('\r', '\n')
                proc.stdin.write(data.encode("utf-8"))
                proc.stdin.flush()
    except (WebSocketDisconnect, ConnectionError):
        pass
    except Exception:
        pass


@router.websocket("/ws/execute")
async def ws_execute(websocket: WebSocket):
    """
    Interactive code execution over WebSocket, running inside Docker.

    Protocol:
      1. Client sends JSON: { "code": "...", "language": "python" }
      2. Server writes code to temp dir, volume-mounts into Docker
      3. Docker runs the code with interactive stdin
      4. Server streams stdout/stderr as text frames
      5. Client sends text frames → piped to container stdin
      6. Server sends final exit status, then closes
    """
    await websocket.accept()

    tmpdir = None
    proc_obj = None

    try:
        # --- 1. Receive init payload ---
        raw = await websocket.receive_text()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            await websocket.send_text(f"{ANSI_RED}Invalid JSON payload.{ANSI_RESET}\r\n")
            await websocket.close()
            return

        code = payload.get("code", "").strip()
        language = payload.get("language", "python").lower()

        print(f"[ws_execute] Received {len(code)} chars of {language} code")

        if not code:
            await websocket.send_text(f"{ANSI_RED}No code provided.{ANSI_RESET}\r\n")
            await websocket.close()
            return

        if language not in LANGUAGE_CONFIG:
            await websocket.send_text(
                f"{ANSI_RED}Unsupported language: '{language}'. "
                f"Use python, c, or cpp.{ANSI_RESET}\r\n"
            )
            await websocket.close()
            return

        # --- 2. Write code to temp dir ---
        tmpdir = tempfile.mkdtemp(prefix="ws_sandbox_")

        if language == "python":
            script_path = os.path.join(tmpdir, "script.py")
            with open(script_path, "w", newline="\n") as f:
                f.write(code)

            # Docker command: mount tmpdir → /code, override entrypoint
            # python3 -u disables output buffering so prompts flush immediately
            docker_args = _docker_base_args() + [
                "-v", f"{tmpdir}:/code",
                "--entrypoint", "python3",
                DOCKER_IMAGE,
                "-u", "/code/script.py",
            ]

        else:
            # C or C++
            config = LANGUAGE_CONFIG[language]
            ext = config["ext"]
            compiler = config["compiler"]
            src_filename = f"code{ext}"
            src_path = os.path.join(tmpdir, src_filename)

            with open(src_path, "w", newline="\n") as f:
                f.write(code)

            await websocket.send_text(
                f"{ANSI_DIM}Compiling {language.upper()} code...{ANSI_RESET}\r\n"
            )

            # Compile + run in a single shell command inside the container.
            # stdbuf forces unbuffered stdout/stderr so prompts appear
            # immediately before scanf/cin blocks, even without newlines.
            shell_cmd = (
                f"{compiler} /code/{src_filename} -o /code/code_exec -lm && "
                f"stdbuf -o0 -e0 /code/code_exec"
            )

            docker_args = _docker_base_args() + [
                "-v", f"{tmpdir}:/code",
                "--entrypoint", "/bin/sh",
                DOCKER_IMAGE,
                "-c", shell_cmd,
            ]

        # --- 3. Spawn Docker container as sync subprocess ---
        print(f"[ws_execute] Docker command: {' '.join(docker_args[:8])}...")
        
        loop = asyncio.get_running_loop()
        proc = subprocess.Popen(
            docker_args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        proc_obj = proc
        
        # --- 4. Launch background threads to stream output ---
        t_out = threading.Thread(target=_stream_output, args=(proc.stdout, websocket, loop, False))
        t_err = threading.Thread(target=_stream_output, args=(proc.stderr, websocket, loop, True))
        t_out.daemon = True
        t_err.daemon = True
        t_out.start()
        t_err.start()
        
        # --- 5. Forward stdin and wait with timeout ---
        stdin_task = asyncio.create_task(_forward_stdin(websocket, proc))
        
        start_time = time.time()
        exit_code = None
        
        while True:
            if proc.poll() is not None:
                exit_code = proc.returncode
                break
            if time.time() - start_time > RUN_TIMEOUT:
                proc.kill()
                proc.wait()
                exit_code = -1
                await websocket.send_text(
                    f"\r\n{ANSI_RED}Process killed: exceeded {RUN_TIMEOUT}s timeout.{ANSI_RESET}\r\n"
                )
                break
            await asyncio.sleep(0.1)
            
        stdin_task.cancel()
        t_out.join(timeout=1.0)
        t_err.join(timeout=1.0)

        # --- 6. Send exit status ---
        if exit_code == 0:
            await websocket.send_text(
                f"\r\n{ANSI_DIM}Process exited with code 0.{ANSI_RESET}\r\n"
            )
        elif exit_code == -1:
            pass  # timeout message already sent
        else:
            await websocket.send_text(
                f"\r\n{ANSI_RED}Process exited with code {exit_code}.{ANSI_RESET}\r\n"
            )

        print(f"[ws_execute] Process exited with code {exit_code}")
        await websocket.close()

    except WebSocketDisconnect:
        # Client disconnected — kill any running container
        print("[ws_execute] Client disconnected")
        if proc_obj and proc_obj.returncode is None:
            proc_obj.kill()

    except Exception as exc:
        print(f"[ws_execute] ERROR: {exc}")
        import traceback
        traceback.print_exc()
        try:
            await websocket.send_text(
                f"\r\n{ANSI_RED}Server error: {exc}{ANSI_RESET}\r\n"
            )
            await websocket.close()
        except Exception:
            pass

    finally:
        # Cleanup temp files
        if tmpdir and os.path.exists(tmpdir):
            shutil.rmtree(tmpdir, ignore_errors=True)

