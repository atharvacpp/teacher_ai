"""
services/ollama_vision.py — Local Ollama LLaVA image analysis.

Uses Ollama's native /api/chat endpoint with streaming enabled so
that generation can be halted mid-stream when the client disconnects.
"""

import requests

from config import OLLAMA_BASE_URL, OLLAMA_VLM_MODEL


def analyze_image(
    b64_image: str,
    prompt: str,
    disconnect_check=None,
) -> str:
    """
    Send a base64-encoded image to the local Ollama server for visual
    analysis via the LLaVA model.

    Uses streaming so that generation can be stopped early if the client
    disconnects (checked via the optional *disconnect_check* callable).

    Args:
        b64_image: Raw base64 string of the image (no data-URI prefix).
        prompt: The user's text prompt to accompany the image.
        disconnect_check: An optional callable that returns True when the
            client has disconnected.  Called after every streamed chunk.

    Returns:
        The model's complete textual response.

    Raises:
        requests.exceptions.ConnectionError: Ollama is not reachable.
        requests.exceptions.Timeout: Ollama took too long to respond.
        RuntimeError: Ollama returned an HTTP error.
    """
    payload = {
        "model": OLLAMA_VLM_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [b64_image],
            }
        ],
        "stream": True,
    }

    print("====== OLLAMA VLM REQUEST DEBUG ======")
    print(f"Ollama URL: {OLLAMA_BASE_URL}/api/chat")
    print(f"Model: {OLLAMA_VLM_MODEL}")
    print(f"Image size: {len(b64_image)} chars (base64)")
    print(f"Prompt: {prompt}")
    print("======================================")

    # Stream the response so we can check for client disconnection
    # between chunks and abort early if needed.
    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json=payload,
        timeout=120,
        stream=True,
    )

    if not resp.ok:
        body = resp.text[:300]
        raise RuntimeError(f"Ollama returned HTTP {resp.status_code}: {body}")

    # Accumulate streamed chunks
    collected_text = []
    for line in resp.iter_lines():
        if not line:
            continue

        # Check if the client has disconnected
        if disconnect_check and disconnect_check():
            print("[ollama_vision] Client disconnected — aborting stream.")
            resp.close()
            break

        import json
        try:
            chunk = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Each streamed chunk has {"message": {"content": "..."}, "done": bool}
        token = chunk.get("message", {}).get("content", "")
        if token:
            collected_text.append(token)

        if chunk.get("done", False):
            break

    return "".join(collected_text)
