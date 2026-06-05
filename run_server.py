import os
import sys
import asyncio
import uvicorn

if __name__ == "__main__":
    # CRITICAL FIX for Windows:
    # Uvicorn's default event loop on Windows (SelectorEventLoop) does not support
    # async subprocesses (which we need for anyio/Docker and the MCP SDK).
    # We must force the ProactorEventLoop BEFORE Uvicorn starts.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    # Run the FastAPI app
    print("Starting ExplainAI Backend with ProactorEventLoop...")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
